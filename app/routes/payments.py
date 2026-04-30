from flask import Blueprint, jsonify, redirect, request
from flask_login import login_required, current_user
from app.models import db, User
import stripe
import os

payments = Blueprint('payments', __name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

PRICE_MAP = {
    'aud': 'STRIPE_PRICE_AUD',
    'usd': 'STRIPE_PRICE_USD',
    'eur': 'STRIPE_PRICE_EUR',
    'gbp': 'STRIPE_PRICE_GBP',
}

@payments.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout():
    currency = request.form.get('currency', 'aud').lower()
    price_env = PRICE_MAP.get(currency, 'STRIPE_PRICE_AUD')
    price_id = os.getenv(price_env)
    if not price_id:
        return jsonify({'error': 'Price not configured for this currency'}), 400

    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        line_items=[{'price': price_id, 'quantity': 1}],
        mode='subscription',
        success_url=request.host_url + 'dashboard?upgrade=success',
        cancel_url=request.host_url + 'dashboard',
    )
    return jsonify({'url': session.url})

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

    if event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        user = User.query.filter_by(stripe_customer_id=subscription.customer).first()
        if not user:
            # Match by email from Stripe customer object
            customer = stripe.Customer.retrieve(subscription['customer'])
            user = User.query.filter_by(email=customer.get('email')).first()
        if user:
            user.plan = 'enterprise'
            user.trial_end = None
            user.stripe_subscription_id = subscription['id']
            user.stripe_customer_id = subscription['customer']
            db.session.commit()

    return jsonify({'status': 'success'})
