from flask import Blueprint, jsonify, redirect, request
from flask_login import login_required, current_user
from app.models import db, User
import stripe
import os

payments = Blueprint('payments', __name__)
stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@payments.route('/create-checkout-session', methods=['POST'])
@login_required
def create_checkout():
    session = stripe.checkout.Session.create(
        customer_email=current_user.email,
        line_items=[{
            'price': os.getenv('STRIPE_ENTERPRISE_PRICE_ID'),
            'quantity': 1,
        }],
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

        if user:
            user.plan = 'enterprise'
            user.stripe_subscription_id = subscription.id
            db.session.commit()

    return jsonify({'status': 'success'})
