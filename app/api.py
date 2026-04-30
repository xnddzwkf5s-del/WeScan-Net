import email
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import User, Recipient, UsageStat

api_bp = Blueprint('api', __name__)


def get_user_from_request():
    """Extract user from SMTP username (sender envelope or header)."""
    username = request.json.get('smtp_username', '') if request.is_json else ''
    if not username:
        return None
    return User.query.filter_by(smtp_username=username).first()


@api_bp.route('/smtp/validate', methods=['POST'])
def smtp_validate():
    """Validated by Postfix content filter before relaying."""
    data = request.get_json(silent=True) or {}
    username = data.get('smtp_username', '')
    recipient_email = data.get('recipient', '').strip().lower()
    file_type = data.get('file_type', '').lower()
    file_size = data.get('file_size', 0)

    user = User.query.filter_by(smtp_username=username).first()
    if not user or not user.is_active:
        return jsonify({'allowed': False, 'reason': 'Invalid account'}), 403

    # Check recipient whitelist
    recipient = Recipient.query.filter_by(
        user_id=user.id, email=recipient_email, is_active=True
    ).first()
    if not recipient:
        return jsonify({'allowed': False, 'reason': 'Recipient not whitelisted'}), 403

    # Check file type
    allowed_types = ['pdf', 'jpg', 'jpeg', 'png']
    if file_type and file_type not in allowed_types:
        return jsonify({'allowed': False, 'reason': f'Only PDF, JPG, PNG allowed'}), 403

    # Check file size
    max_bytes = user.file_size_limit_mb * 1024 * 1024
    if file_size > max_bytes:
        return jsonify({'allowed': False, 'reason': f'Limit is {user.file_size_limit_mb}MB'}), 403

    return jsonify({'allowed': True})


@api_bp.route('/smtp/log', methods=['POST'])
def smtp_log():
    """Log a sent email."""
    data = request.get_json(silent=True) or {}
    username = data.get('smtp_username', '')
    user = User.query.filter_by(smtp_username=username).first()
    if not user:
        return jsonify({'logged': False}), 200

    stat = UsageStat(
        user_id=user.id,
        recipient_email=data.get('recipient', ''),
        file_type=data.get('file_type', ''),
        file_size_bytes=data.get('file_size', 0),
        status=data.get('status', 'delivered')
    )
    db.session.add(stat)
    db.session.commit()
    return jsonify({'logged': True})


@api_bp.route('/health')
def health():
    return jsonify({'status': 'ok'})
