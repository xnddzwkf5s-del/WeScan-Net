from flask import Blueprint, jsonify, redirect, request
from flask_login import login_required, current_user
from app.models import db, User
import stripe
import os
from datetime import datetime

payments = Blueprint('payments', __name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

PRICE_MAP = {
    'pro': {
        'aud': 'STRIPE_PRICE_PRO_AUD',
        'usd': 'STRIPE_PRICE_PRO_USD',
        'eur': 'STRIPE_PRICE_PRO_EUR',
        'gbp': 'STRIPE_PRICE_PRO_GBP',
    },
    'business': {
        'aud': 'STRIPE_PRICE_BUS_AUD',
        'usd': 'STRIPE_PRICE_BUS_USD',
        'eur': 'STRIPE_PRICE_BUS_EUR',
        'gbp': 'STRIPE_PRICE_BUS_GBP',
    },
    'enterprise': {
        'aud': 'STRIPE_PRICE_ENT_AUD',
        'usd': 'STRIPE_PRICE_ENT_USD',
        'eur': 'STRIPE_PRICE_ENT_EUR',
        'gbp': 'STRIPE_PRICE_ENT_GBP',
    },
}

@payments.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout():
    currency = request.form.get('currency', 'aud').lower()
    plan = request.form.get('plan', 'enterprise').lower()

    plan_prices = PRICE_MAP.get(plan)
    if not plan_prices:
        return jsonify({'error': 'Invalid plan'}), 400

    price_env = plan_prices.get(currency, plan_prices.get('aud'))
    price_id = os.getenv(price_env)
    if not price_id:
        return jsonify({'error': 'Price not configured for this currency'}), 400

    # Create or reuse Stripe customer so portal works later
    customer_id = current_user.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(email=current_user.email)
        customer_id = customer.id
        current_user.stripe_customer_id = customer_id
        db.session.commit()

    session = stripe.checkout.Session.create(
        customer=customer_id,
        line_items=[{'price': price_id, 'quantity': 1}],
        mode='subscription',
        success_url=request.host_url + 'dashboard?upgrade=success',
        cancel_url=request.host_url + 'dashboard',
    )
    return jsonify({'url': session.url})


@payments.route('/billing-portal', methods=['POST'])
@login_required
def billing_portal():
    if not current_user.stripe_customer_id:
        return jsonify({'error': 'No billing account found'}), 400
    portal = stripe.billing_portal.Session.create(
        customer=current_user.stripe_customer_id,
        return_url=request.host_url + 'dashboard',
    )
    return jsonify({'url': portal.url})

@payments.route('/webhook', methods=['POST'])
def webhook():
    event = None
    payload = request.data
    sig_header = request.headers['STRIPE_SIGNATURE']

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.getenv('STRIPE_WEBHOOK_SECRET')
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400

    subscription = event['data']['object']
    event_type = event['type']

    def find_user(subscription):
        user = User.query.filter_by(stripe_customer_id=subscription['customer']).first()
        if not user:
            customer = stripe.Customer.retrieve(subscription['customer'])
            user = User.query.filter_by(email=customer.get('email')).first()
        return user

    def plan_from_price_id(price_id):
        """Map a Stripe price ID to a plan name."""
        # Check which env var matches this price ID
        price_env_map = {
            'STRIPE_PRICE_PRO_AUD': 'pro', 'STRIPE_PRICE_PRO_USD': 'pro',
            'STRIPE_PRICE_PRO_EUR': 'pro', 'STRIPE_PRICE_PRO_GBP': 'pro',
            'STRIPE_PRICE_BUS_AUD': 'business', 'STRIPE_PRICE_BUS_USD': 'business',
            'STRIPE_PRICE_BUS_EUR': 'business', 'STRIPE_PRICE_BUS_GBP': 'business',
            'STRIPE_PRICE_ENT_AUD': 'enterprise', 'STRIPE_PRICE_ENT_USD': 'enterprise',
            'STRIPE_PRICE_ENT_EUR': 'enterprise', 'STRIPE_PRICE_ENT_GBP': 'enterprise',
        }
        for env_var, plan_name in price_env_map.items():
            if os.getenv(env_var) == price_id:
                return plan_name
        return 'enterprise'  # fallback

    if event_type == 'customer.subscription.created':
        user = find_user(subscription)
        if user:
            items = subscription.get('items', {}).get('data', [])
            price_id = items[0]['price']['id'] if items else None
            plan = plan_from_price_id(price_id) if price_id else 'enterprise'
            user.plan = plan
            user.trial_end = None
            user.stripe_subscription_id = subscription['id']
            user.stripe_customer_id = subscription['customer']
            db.session.commit()

    elif event_type == 'customer.subscription.deleted':
        # Subscription fully cancelled — downgrade immediately
        user = find_user(subscription)
        if user:
            user.plan = 'free'
            user.trial_end = None
            user.stripe_subscription_id = None
            db.session.commit()

    elif event_type == 'customer.subscription.updated':
        user = find_user(subscription)
        if user:
            status = subscription.get('status')
            cancel_at_period_end = subscription.get('cancel_at_period_end', False)
            cancel_at = subscription.get('cancel_at')

            if status == 'active' and not cancel_at_period_end:
                # Reactivated, renewed, or plan changed — detect the plan
                items = subscription.get('items', {}).get('data', [])
                price_id = items[0]['price']['id'] if items else None
                user.plan = plan_from_price_id(price_id) if price_id else 'enterprise'
                user.trial_end = None
            elif cancel_at_period_end and cancel_at:
                # Scheduled to cancel — set trial_end to period end so banner shows
                user.trial_end = datetime.utcfromtimestamp(cancel_at)
            elif status in ('canceled', 'unpaid', 'past_due'):
                user.plan = 'free'
                user.trial_end = None
                user.stripe_subscription_id = None
            db.session.commit()

    return jsonify({'status': 'success'})
