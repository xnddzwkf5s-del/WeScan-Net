from flask import Blueprint, request, jsonify
from app.models import db, User, Recipient, UsageStat
from email_validator import validate_email, EmailNotValidError

smtp = Blueprint('smtp', __name__)

@smtp.route('/api/smtp/validate', methods=['POST'])
def validate():
    data = request.json
    sender = data['sender']
    recipient = data['recipient']

    # Validate email format
    try:
        validate_email(recipient)
    except EmailNotValidError:
        return 'Invalid email format', 400

    # Get user from sender
    user = User.query.filter_by(smtp_username=sender).first()
    if not user or not user.is_active:
        return 'Invalid sender', 403

    # Check recipient whitelist
    whitelist = Recipient.query.filter_by(
        user_id=user.id,
        email=recipient,
        is_active=True
    ).first()

    if not whitelist:
        return 'Recipient not whitelisted', 403

    return 'OK', 200
