import email
import re
from flask import Blueprint, request, jsonify, current_app
from app import db
from app.models import User, Recipient, UsageStat, Document
from datetime import datetime, timedelta
import base64

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
        return jsonify({'allowed': False, 'reason': 'Only PDF, JPG, PNG allowed'}), 403

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


@api_bp.route('/api/documents/store', methods=['POST'])
def store_document():
    """Store an incoming scanned document (called by content filter)."""
    if request.is_json:
        data = request.get_json(silent=True) or {}
        raw_email_b64 = data.get('email_data', '')
        smtp_username = data.get('smtp_username', '')
        recipient = data.get('recipient', '')
        raw_email = base64.b64decode(raw_email_b64) if raw_email_b64 else b''
    else:
        raw_email = request.files.get('email_data').read() if request.files.get('email_data') else b''
        smtp_username = request.form.get('smtp_username', '')
        recipient = request.form.get('recipient', '')

    if not raw_email or not smtp_username:
        return jsonify({'error': 'Missing email_data or smtp_username'}), 400

    user = User.query.filter_by(smtp_username=smtp_username).first()
    if not user or not user.is_active:
        return jsonify({'error': 'Invalid user'}), 403

    try:
        msg = email.message_from_bytes(raw_email)
    except Exception:
        return jsonify({'error': 'Could not parse email'}), 400

    # Check storage quota
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == user.id
    ).scalar() or 0
    limit_mb = 200 if user.plan == 'enterprise' else 15
    limit_bytes = limit_mb * 1024 * 1024

    pdf_filename = None
    pdf_data = None

    def _extract_pdf_part(part):
        nonlocal pdf_filename, pdf_data
        if pdf_data:
            return
        content_type = part.get_content_type()
        content_disposition = str(part.get('Content-Disposition', ''))
        if content_type == 'application/pdf' or 'filename' in content_disposition.lower():
            payload = part.get_payload(decode=True)
            if payload:
                if payload.startswith(b'%PDF-') or content_type == 'application/pdf':
                    pdf_filename = part.get_filename() or 'scanned-document.pdf'
                    pdf_data = payload

    if msg.is_multipart():
        for part in msg.walk():
            _extract_pdf_part(part)
            if pdf_data:
                break
    else:
        _extract_pdf_part(msg)

    if not pdf_data:
        payload = msg.get_payload(decode=True)
        if payload and payload.startswith(b'%PDF-'):
            pdf_data = payload
            pdf_filename = 'scanned-document.pdf'

    if not pdf_data:
        return jsonify({'error': 'No PDF attachment found'}), 400

    if len(pdf_data) > limit_bytes:
        return jsonify({'error': f'File exceeds {limit_mb}MB storage limit'}), 413
    if storage_used + len(pdf_data) > limit_bytes:
        return jsonify({'error': 'Storage quota exceeded'}), 413

    doc = Document(
        user_id=user.id,
        filename=pdf_filename or 'scanned-document.pdf',
        file_data=pdf_data,
        file_size=len(pdf_data),
        mime_type='application/pdf',
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=14)
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'ok': True, 'document_id': doc.id, 'filename': doc.filename})


@api_bp.route('/api/documents/inbox-store', methods=['POST'])
def inbox_store_document():
    """Store a document forwarded to a user's dedicated inbox address.
    Called by content filter when mail arrives for i-xxxx@inbox.wescan.net"""
    data = request.get_json(silent=True) or {}
    raw_email_b64 = data.get('email_data', '')
    inbox_address = data.get('inbox_address', '')

    if not raw_email_b64 or not inbox_address:
        return jsonify({'error': 'Missing email_data or inbox_address'}), 400

    user = User.query.filter_by(inbox_address=inbox_address).first()
    if not user or not user.is_active:
        return jsonify({'error': 'Invalid inbox address'}), 404

    raw_email = base64.b64decode(raw_email_b64)

    import email as emaillib
    try:
        msg = emaillib.message_from_bytes(raw_email)
    except Exception:
        return jsonify({'error': 'Could not parse email'}), 400

    pdf_filename = None
    pdf_data = None

    def _extract_pdf_part(part):
        nonlocal pdf_filename, pdf_data
        if pdf_data:
            return
        ct = part.get_content_type()
        cd = str(part.get('Content-Disposition', ''))
        if ct == 'application/pdf' or 'filename' in cd.lower():
            payload = part.get_payload(decode=True)
            if payload:
                if payload.startswith(b'%PDF-') or ct == 'application/pdf':
                    pdf_filename = part.get_filename() or 'forwarded-document.pdf'
                    pdf_data = payload

    if msg.is_multipart():
        for part in msg.walk():
            _extract_pdf_part(part)
            if pdf_data:
                break
    else:
        _extract_pdf_part(msg)

    if not pdf_data:
        payload = msg.get_payload(decode=True)
        if payload and payload.startswith(b'%PDF-'):
            pdf_data = payload
            pdf_filename = 'forwarded-document.pdf'

    if not pdf_data:
        return jsonify({'error': 'No PDF attachment found'}), 400

    # Storage quota check
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == user.id
    ).scalar() or 0
    limit_mb = 200 if user.plan == 'enterprise' else 15
    limit_bytes = limit_mb * 1024 * 1024
    if len(pdf_data) > limit_bytes:
        return jsonify({'error': f'File exceeds {limit_mb}MB storage limit'}), 413
    if storage_used + len(pdf_data) > limit_bytes:
        return jsonify({'error': 'Storage quota exceeded'}), 413

    doc = Document(
        user_id=user.id,
        filename=pdf_filename or 'forwarded-document.pdf',
        file_data=pdf_data,
        file_size=len(pdf_data),
        mime_type='application/pdf',
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=14)
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'ok': True, 'document_id': doc.id, 'filename': doc.filename, 'from': 'inbox'})
