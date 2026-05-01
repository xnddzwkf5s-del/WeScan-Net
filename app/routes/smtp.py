from flask import Blueprint, request, jsonify
from app.models import db, User, Recipient, UsageStat, BlockedEmail
from email_validator import validate_email, EmailNotValidError
from datetime import datetime, timedelta

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

    # Hourly rate limit for free plan
    if user.plan == 'free':
        hour_ago = datetime.utcnow() - timedelta(hours=1)
        emails_this_hour = UsageStat.query.filter(
            UsageStat.user_id == user.id,
            UsageStat.sent_at >= hour_ago
        ).count()
        if emails_this_hour >= 5:
            block = BlockedEmail(
                user_id=user.id,
                smtp_username=smtp_user,
                attempted_recipient=recipient,
                reason='rate_limit_exceeded'
            )
            db.session.add(block)
            db.session.commit()
            return 'Rate limit exceeded. Essential plan allows 5 emails per hour.', 429

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

    return jsonify({'ok': True, 'user_id': user.id}), 200


@smtp.route('/api/smtp/record', methods=['POST'])
def record_sent():
    """Called by content filter after successful Mailgun delivery."""
    data      = request.json or {}
    user_id   = data.get('user_id')
    recipient = data.get('recipient', '')
    file_size = data.get('file_size_bytes', 0)

    if not user_id:
        return 'Missing user_id', 400

    # Check if this user had a pending verification
    user = User.query.get(user_id)
    if user and user.verify_requested_at and not user.scan_verified_at:
        now = datetime.utcnow()
        # Mark verified if first scan arrives within 1 hour of request
        if now - user.verify_requested_at < timedelta(hours=1):
            user.scan_verified_at = now

    stat = UsageStat(
        user_id=user_id,
        recipient_email=recipient,
        file_size_bytes=file_size,
        status='sent'
    )
    db.session.add(stat)
    db.session.commit()
    return 'OK', 200
