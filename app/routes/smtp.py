from flask import Blueprint, request, jsonify
from app.models import db, User, Recipient, UsageStat, BlockedEmail
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

    # Get user from sender (strip @domain if present)
    smtp_user = sender.split('@')[0] if '@' in sender else sender
    user = User.query.filter_by(smtp_username=smtp_user).first()
    if not user or not user.is_active:
        block = BlockedEmail(
            smtp_username=smtp_user,
            attempted_recipient=recipient,
            reason='unknown_user'
        )
        db.session.add(block)
        db.session.commit()
        return 'Invalid sender', 403

    # Check recipient whitelist
    whitelist = Recipient.query.filter_by(
        user_id=user.id,
        email=recipient,
        is_active=True
    ).first()

    if not whitelist:
        block = BlockedEmail(
            user_id=user.id,
            smtp_username=smtp_user,
            attempted_recipient=recipient,
            reason='not_whitelisted'
        )
        db.session.add(block)
        db.session.commit()
        return 'Recipient not whitelisted', 403

    return 'OK', 200
