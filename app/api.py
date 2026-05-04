import email
import re
from flask import Blueprint, request, jsonify, current_app, render_template
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
    from app.routes.dashboard import PLAN_LIMITS
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == user.id
    ).scalar() or 0
    limit_mb = PLAN_LIMITS.get(user.plan, PLAN_LIMITS['free'])['storage_mb']
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

    retention_days = PLAN_LIMITS.get(user.plan, PLAN_LIMITS['free'])['doc_retention_days']
    doc = Document(
        user_id=user.id,
        filename=pdf_filename or 'scanned-document.pdf',
        file_data=pdf_data,
        file_size=len(pdf_data),
        mime_type='application/pdf',
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=retention_days)
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

    from app.routes.dashboard import PLAN_LIMITS
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == user.id
    ).scalar() or 0
    limit_mb = PLAN_LIMITS.get(user.plan, PLAN_LIMITS['free'])['storage_mb']
    limit_bytes = limit_mb * 1024 * 1024
    retention_days = PLAN_LIMITS.get(user.plan, PLAN_LIMITS['free'])['doc_retention_days']

    # Extract ALL PDF attachments, not just the first one
    pdf_parts = []

    def _extract_all_pdfs(part):
        ct = part.get_content_type()
        cd = str(part.get('Content-Disposition', ''))
        if ct == 'application/pdf' or 'filename' in cd.lower():
            payload = part.get_payload(decode=True)
            if payload:
                if payload.startswith(b'%PDF-') or ct == 'application/pdf':
                    fname = part.get_filename() or 'forwarded-document.pdf'
                    pdf_parts.append((fname, payload))

    if msg.is_multipart():
        for part in msg.walk():
            _extract_all_pdfs(part)
    else:
        _extract_all_pdfs(msg)

    # If no PDF via MIME, try raw payload
    if not pdf_parts:
        payload = msg.get_payload(decode=True)
        if payload and payload.startswith(b'%PDF-'):
            pdf_parts.append(('forwarded-document.pdf', payload))

    if not pdf_parts:
        return jsonify({'error': 'No PDF attachment found'}), 400

    # Check total quota across all PDFs
    total_new_size = sum(len(p) for _, p in pdf_parts)
    if total_new_size > limit_bytes:
        return jsonify({'error': f'Total file size exceeds {limit_mb}MB storage limit'}), 413
    if storage_used + total_new_size > limit_bytes:
        return jsonify({'error': 'Storage quota exceeded'}), 413

    # Store each PDF as a separate document
    stored_ids = []
    for fname, data in pdf_parts:
        doc = Document(
            user_id=user.id,
            filename=fname,
            file_data=data,
            file_size=len(data),
            mime_type='application/pdf',
            status='pending',
            expires_at=datetime.utcnow() + timedelta(days=retention_days)
        )
        db.session.add(doc)
        db.session.flush()  # flush to get doc.id assigned
        stored_ids.append({'document_id': doc.id, 'filename': fname})

    db.session.commit()

    # Return first one as primary, list of all in 'documents'
    first = stored_ids[0]
    return jsonify({
        'ok': True,
        'document_id': first['document_id'],
        'filename': first['filename'],
        'documents': stored_ids,
        'count': len(stored_ids),
        'from': 'inbox'
    })


# ── Public share link ─────────────────────────────────────────────────────

@api_bp.route('/share/<token>')
def shared_download(token):
    from app.models import SharedLink
    from flask import render_template
    link = SharedLink.query.filter_by(token=token, is_active=True).first()
    if not link or link.expires_at < datetime.utcnow():
        return render_template('share_expired.html'), 410
    return render_template(
        'share.html',
        filename=link.document.filename,
        file_size=link.document.file_size,
        download_count=link.download_count,
        expires_at=link.expires_at,
        token=token
    )


@api_bp.route('/share/<token>/download')
def shared_download_file(token):
    from app.models import SharedLink
    from flask import send_file
    import io
    link = SharedLink.query.filter_by(token=token, is_active=True).first()
    if not link or link.expires_at < datetime.utcnow():
        return render_template('share_expired.html'), 410
    link.download_count += 1
    db.session.commit()
    return send_file(
        io.BytesIO(link.document.file_data),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=link.document.filename
    )
