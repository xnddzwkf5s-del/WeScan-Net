from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.models import db, User, Recipient, UsageStat, BlockedEmail, Document, Signature, SignedDocument
from datetime import datetime, timedelta
import subprocess
import os
import io
import base64
import smtplib
from email.mime.text import MIMEText
from werkzeug.security import generate_password_hash
from app.pdf_utils import pdf_page_as_png, pdf_page_count, overlay_signature_on_pdf, overlay_signature_on_pdf_multi
from app.email import send_with_attachment

dashboard = Blueprint('dashboard', __name__)

# ── Plan limits (shared, importable by smtp.py) ─────────────────────
PLAN_LIMITS = {
    'free':       {'recipients': 3,   'storage_mb': 15,   'file_size_mb': 10,  'sends_per_month': 10,   'emails_per_hour': 5,    'doc_retention_days': 7,   'max_signatures': 1,    'enterprise_features': False},
    'pro':        {'recipients': 15,  'storage_mb': 100,  'file_size_mb': 25,  'sends_per_month': 50,   'emails_per_hour': 50,   'doc_retention_days': 30,  'max_signatures': 3,    'enterprise_features': False},
    'business':   {'recipients': 50,  'storage_mb': 500,  'file_size_mb': 50,  'sends_per_month': None, 'emails_per_hour': None, 'doc_retention_days': 90,  'max_signatures': 10,   'enterprise_features': True},
    'enterprise': {'recipients': 100, 'storage_mb': 2048, 'file_size_mb': 100, 'sends_per_month': None, 'emails_per_hour': None, 'doc_retention_days': 365, 'max_signatures': None, 'enterprise_features': True},
}

PLAN_NAMES = {
    'free': 'Free',
    'pro': 'Pro',
    'business': 'Business',
    'enterprise': 'Enterprise',
}


def get_plan_limits(user):
    """Get the limit dict for a user's plan, defaulting to free."""
    return PLAN_LIMITS.get(user.plan, PLAN_LIMITS['free'])


def plan_display_name(plan):
    """Return a human-readable plan name."""
    return PLAN_NAMES.get(plan, plan.capitalize())


def get_upgrade_options(current_plan):
    """Return list of plans the user can upgrade to (plans above their current tier)."""
    order = ['free', 'pro', 'business', 'enterprise']
    current_idx = order.index(current_plan) if current_plan in order else 0
    return [p for p in order if order.index(p) > current_idx]


@dashboard.route('/dashboard')
@login_required
def index():
    now        = datetime.utcnow()
    cutoff_1d  = now - timedelta(days=1)
    cutoff_7d  = now - timedelta(days=7)
    cutoff_30d = now - timedelta(days=30)

    recipients = Recipient.query.filter_by(user_id=current_user.id, is_active=True).all()
    usage      = UsageStat.query.filter_by(user_id=current_user.id)\
                    .order_by(UsageStat.sent_at.desc()).limit(10).all()

    blocked_recent = BlockedEmail.query\
        .filter_by(user_id=current_user.id)\
        .filter(BlockedEmail.blocked_at > cutoff_30d)\
        .order_by(BlockedEmail.blocked_at.desc()).limit(10).all()

    # Trial / cancellation state
    trial_days_left = None
    trial_expired = False
    cancelling = False
    if current_user.trial_end:
        delta = (current_user.trial_end - now).days
        if delta >= 0:
            if current_user.stripe_subscription_id:
                cancelling = True
                trial_days_left = delta
            else:
                trial_days_left = delta
        else:
            trial_expired = True

    # Scan verification state
    scan_verify_status = 'none'
    if current_user.scan_verified_at:
        scan_verify_status = 'verified'
    elif current_user.verify_requested_at:
        if datetime.utcnow() - current_user.verify_requested_at > timedelta(hours=1):
            scan_verify_status = 'expired'
        else:
            scan_verify_status = 'waiting'

    # ── Document Inbox data ──
    now_utc = datetime.utcnow()
    documents_list = Document.query.filter(
        Document.user_id == current_user.id,
        Document.expires_at > now_utc,
        Document.status != 'expired'
    ).order_by(Document.created_at.desc()).all()

    # Storage usage
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == current_user.id
    ).scalar() or 0
    limits = get_plan_limits(current_user)
    storage_limit_mb = limits['storage_mb']
    storage_used_mb = round(storage_used / (1024 * 1024), 1)

    # Signatures
    signatures_list = Signature.query.filter_by(user_id=current_user.id).all()

    # Sent documents
    sent_documents = SignedDocument.query.filter_by(user_id=current_user.id)\
        .order_by(SignedDocument.created_at.desc()).limit(20).all()

    # Monthly signed send count for quota display
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    signed_sends_this_month = SignedDocument.query.filter(
        SignedDocument.user_id == current_user.id,
        SignedDocument.created_at >= month_start
    ).count()

    signed_send_limit = limits['sends_per_month']  # None = unlimited

    # Inbox address
    inbox_slug = current_user.inbox_address
    inbox_full = f'{inbox_slug}@inbox.wescan.net' if inbox_slug else None

    stats = {
        'emails_30d':      UsageStat.query.filter_by(user_id=current_user.id)
                            .filter(UsageStat.sent_at > cutoff_30d).count(),
        'blocked_30d':     BlockedEmail.query.filter_by(user_id=current_user.id)
                            .filter(BlockedEmail.blocked_at > cutoff_30d).count(),
        'recipient_limit': limits['recipients'],
        'doc_count':       len(documents_list),
        'send_count':      signed_sends_this_month,
        'recipient_count': len(recipients),
    }

    return render_template('dashboard/index.html',
        user=current_user,
        recipients=recipients,
        usage=usage,
        stats=stats,
        blocked_recent=blocked_recent,
        trial_days_left=trial_days_left,
        trial_expired=trial_expired,
        cancelling=cancelling,
        scan_verify_status=scan_verify_status,
        documents=documents_list,
        signatures=signatures_list,
        sent_documents=sent_documents,
        storage_used_mb=storage_used_mb,
        storage_limit_mb=storage_limit_mb,
        signed_sends_this_month=signed_sends_this_month,
        signed_send_limit=signed_send_limit,
        inbox_full=inbox_full,
        PLAN_NAMES=PLAN_NAMES,
        limits=limits,
        get_upgrade_options=get_upgrade_options
    )

@dashboard.route('/dashboard/smtp/generate', methods=['POST'])
@login_required
def generate_smtp_password():
    password = os.urandom(12).hex()

    subprocess.run([
        '/usr/bin/sudo',
        '/opt/wescan/scripts/manage-sasl.sh',
        'add',
        current_user.smtp_username,
        password
    ], check=True)

    current_user.smtp_password_hash = generate_password_hash(password)
    db.session.commit()

    return jsonify({
        'smtp_username': current_user.smtp_username,
        'smtp_password': password
    })

@dashboard.route('/dashboard/send-test-email', methods=['POST'])
@login_required
def send_test_email():
    """Send a test email to the user to prove the SMTP server works."""
    email = current_user.email
    try:
        msg = MIMEText(f"""Hi {current_user.name or 'there'},\n\nThis is a test email from WeScan.\n\nIf you received this, your WeScan SMTP server is working correctly.\nNow configure your scanner to send emails through us.\n\n---\nSMTP Server: smtp.wescan.net\nPort: 587\nEncryption: STARTTLS\nUsername: {current_user.smtp_username}\n\n— WeScan Team\nhttps://wescan.net""")
        msg['Subject'] = 'Your WeScan test email — SMTP is working'
        msg['From'] = 'noreply@wescan.net'
        msg['To'] = email

        with smtplib.SMTP('127.0.0.1', 25) as s:
            s.send_message(msg)

        return jsonify({'ok': True, 'message': 'Test email sent to ' + email}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500


@dashboard.route('/dashboard/verify-scan', methods=['GET', 'POST'])
@login_required
def verify_scan():
    if request.method == 'POST':
        # Initiate verification request
        current_user.verify_requested_at = datetime.utcnow()
        current_user.scan_verified_at = None
        db.session.commit()
        return jsonify({'ok': True, 'status': 'waiting'}), 200

    # GET — return current status
    if current_user.scan_verified_at:
        return jsonify({'ok': True, 'status': 'verified'}), 200
    elif current_user.verify_requested_at:
        delta = datetime.utcnow() - current_user.verify_requested_at
        if delta > timedelta(hours=1):
            return jsonify({'ok': True, 'status': 'expired'}), 200
        return jsonify({'ok': True, 'status': 'waiting', 'since_total_seconds': int(delta.total_seconds())}), 200
    else:
        return jsonify({'ok': True, 'status': 'not_requested'}), 200


@dashboard.route('/dashboard/recipients', methods=['GET', 'POST'])
@login_required
def manage_recipients():
    if request.method == 'POST':
        email = request.form['email']
        name = request.form['name']

        current_count = Recipient.query.filter_by(
            user_id=current_user.id,
            is_active=True
        ).count()

        limits = get_plan_limits(current_user)
        limit = limits['recipients']
        if current_count >= limit:
            return 'Recipient limit reached', 400

        recipient = Recipient(
            email=email,
            display_name=name,
            user_id=current_user.id
        )
        db.session.add(recipient)
        db.session.commit()
        flash(f'{email} added as a recipient.', 'success')
    else:
        flash('Email is required.', 'error')

    return redirect(url_for('dashboard.index'))

@dashboard.route('/dashboard/recipients/<int:id>/delete', methods=['POST'])
@login_required
def delete_recipient(id):
    recipient = Recipient.query.get_or_404(id)
    if recipient.user_id == current_user.id:
        email = recipient.email
        db.session.delete(recipient)
        db.session.commit()
        flash(f'{email} removed.', 'success')
    return redirect(url_for('dashboard.index'))


# ── Document Inbox Endpoints ──

@dashboard.route('/dashboard/documents', methods=['GET'])
@login_required
def list_documents():
    now_utc = datetime.utcnow()
    docs = Document.query.filter(
        Document.user_id == current_user.id,
        Document.expires_at > now_utc,
        Document.status != 'expired'
    ).order_by(Document.created_at.desc()).all()
    return jsonify([{
        'id': d.id,
        'filename': d.filename,
        'file_size': d.file_size,
        'status': d.status,
        'created_at': d.created_at.isoformat(),
        'expires_at': d.expires_at.isoformat()
    } for d in docs])


@dashboard.route('/dashboard/documents/upload', methods=['POST'])
@login_required
def upload_document():
    """Upload a PDF directly to the Document Inbox."""
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': 'No file uploaded'}), 400

    raw = f.read()
    if not raw:
        return jsonify({'error': 'Empty file'}), 400

    # Validate it's a PDF
    from app.pdf_utils import pdf_page_count
    page_count = pdf_page_count(raw)
    if page_count == 0:
        return jsonify({'error': 'Not a valid PDF or file has no pages'}), 400

    # Check storage limit
    limits = get_plan_limits(current_user)
    storage_limit_bytes = limits['storage_mb'] * 1024 * 1024
    storage_used = db.session.query(db.func.sum(Document.file_size)).filter(
        Document.user_id == current_user.id
    ).scalar() or 0
    if storage_used + len(raw) > storage_limit_bytes:
        return jsonify({'error': f'Storage limit reached ({limits["storage_mb"]} MB). Delete some documents or upgrade.'}), 413

    # Clean filename
    filename = f.filename.rsplit('.', 1)[0][:80]
    if not filename.lower().endswith('.pdf'):
        filename += '.pdf'

    doc = Document(
        user_id=current_user.id,
        filename=filename,
        file_data=raw,
        file_size=len(raw),
        mime_type='application/pdf',
        status='pending',
        expires_at=datetime.utcnow() + timedelta(days=14)
    )
    db.session.add(doc)
    db.session.commit()

    return jsonify({'ok': True, 'id': doc.id, 'filename': doc.filename}), 201


@dashboard.route('/dashboard/documents/<int:doc_id>/download', methods=['GET'])
@login_required
def download_document(doc_id):
    from flask import send_file
    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return 'Not found', 404
    if doc.expires_at < datetime.utcnow():
        return 'Document expired', 410
    return send_file(
        io.BytesIO(doc.file_data),
        mimetype=doc.mime_type or 'application/pdf',
        as_attachment=True,
        download_name=doc.filename
    )


@dashboard.route('/dashboard/documents/<int:doc_id>', methods=['DELETE'])
@login_required
def delete_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'ok': True})


@dashboard.route('/dashboard/documents/<int:doc_id>/preview', methods=['GET'])
@login_required
def preview_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404
    if doc.expires_at < datetime.utcnow():
        return jsonify({'error': 'Document expired'}), 410

    page = request.args.get('page', 0, type=int)
    page = max(0, page)
    page_count = pdf_page_count(doc.file_data)

    if page >= page_count:
        return jsonify({'error': 'Page out of range'}), 400

    png_b64 = pdf_page_as_png(doc.file_data, page)
    if not png_b64:
        return jsonify({'error': 'Could not render PDF'}), 500

    return jsonify({
        'id': doc.id,
        'filename': doc.filename,
        'preview': png_b64,
        'page_count': page_count,
        'current_page': page,
        'file_size': doc.file_size
    })


@dashboard.route('/dashboard/documents/<int:doc_id>/sign', methods=['GET'])
@login_required
def sign_document_page(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        abort(404)
    if doc.expires_at < datetime.utcnow():
        flash('This document has expired.', 'error')
        return redirect(url_for('dashboard.index'))

    signatures_list = Signature.query.filter_by(user_id=current_user.id).all()

    now_utc = datetime.utcnow()
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    signed_sends_this_month = SignedDocument.query.filter(
        SignedDocument.user_id == current_user.id,
        SignedDocument.created_at >= month_start
    ).count()
    limits = get_plan_limits(current_user)
    signed_send_limit = limits['sends_per_month']

    return render_template('dashboard/sign.html',
        user=current_user,
        doc=doc,
        signatures=signatures_list,
        signed_sends_this_month=signed_sends_this_month,
        signed_send_limit=signed_send_limit
    )


@dashboard.route('/dashboard/documents/<int:doc_id>/sign-and-send', methods=['POST'])
@login_required
def sign_and_send(doc_id):
    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404
    if doc.expires_at < datetime.utcnow():
        return jsonify({'error': 'Document expired'}), 410
    # Allow re-signing — status check removed, user confirms in UI

    data = request.get_json(silent=True) or {}
    signature_id = data.get('signature_id')
    sig_x = float(data.get('position_x', 0.5)) if 'position_x' in data else None
    sig_y = float(data.get('position_y', 0.85)) if 'position_y' in data else None
    sig_page = int(data.get('page_number', 0)) if 'page_number' in data else None
    placements = data.get('placements')
    additional_recipients = data.get('additional_recipients', '').strip()
    timestamp_enabled = bool(data.get('timestamp_enabled', False))
    timestamp_tz = str(data.get('timestamp_tz', 'UTC')).strip() or 'UTC'

    # signature_id is optional when placements carry per-placement sig_id
    signature = None
    if signature_id:
        signature = Signature.query.filter_by(id=signature_id, user_id=current_user.id).first()
    if not signature and placements:
        # Use the first placement's sig_id as the fallback signature
        first_sig_id = placements[0].get('sig_id') if placements else None
        if first_sig_id:
            signature = Signature.query.filter_by(id=first_sig_id, user_id=current_user.id).first()
    if not signature:
        return jsonify({'error': 'Signature not found'}), 404

    # ── Quota check ──
    now_utc = datetime.utcnow()
    month_start = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    limits = get_plan_limits(current_user)
    send_limit = limits['sends_per_month']
    if send_limit is not None:
        count = SignedDocument.query.filter(
            SignedDocument.user_id == current_user.id,
            SignedDocument.sent_at >= month_start
        ).count()
        if count >= send_limit:
            return jsonify({'error': 'Monthly signed-send limit reached. Upgrade to Business or Enterprise for unlimited sends.'}), 403

    # ── Overlay signature(s) on PDF ──
    try:
        if placements:
            # Multi-page placements — each may use a different signature
            placement_list = []
            sig_cache = {signature.id: signature}
            for p in placements:
                sig_id = p.get('sig_id') or signature_id
                if sig_id not in sig_cache:
                    s = Signature.query.filter_by(id=sig_id, user_id=current_user.id).first()
                    if s:
                        sig_cache[sig_id] = s
                sig_obj = sig_cache.get(sig_id, signature)
                placement_list.append({
                    'page': int(p.get('page', 0)),
                    'x': float(p.get('x', 0.5)),
                    'y': float(p.get('y', 0.85)),
                    'sigData': sig_obj.data,
                    'sigScale': float(p.get('sig_scale', 0.25))
                })
            signed_pdf_bytes = overlay_signature_on_pdf_multi(doc.file_data, placement_list, timestamp_enabled=timestamp_enabled, timestamp_tz=timestamp_tz)
            # Use the first placement for the signed document record
            sig_x = float(placements[0].get('x', 0.5))
            sig_y = float(placements[0].get('y', 0.85))
            sig_page = int(placements[0].get('page', 0))
        else:
            # Fallback: single-page placement
            if sig_x is None:
                sig_x = 0.5
            if sig_y is None:
                sig_y = 0.85
            if sig_page is None:
                sig_page = 0
            signed_pdf_bytes = overlay_signature_on_pdf(
                doc.file_data, signature.data,
                sig_x, sig_y, sig_page,
                timestamp_enabled=timestamp_enabled, timestamp_tz=timestamp_tz
            )
    except Exception as e:
        return jsonify({'error': f'Failed to sign PDF: {str(e)}'}), 500

    # ── Parse additional recipients ──
    extra_recipients = []
    if additional_recipients:
        extra_recipients = [
            r.strip() for r in additional_recipients.split('\n')
            if r.strip() and '@' in r.strip()
        ]

    # ── Send via Mailgun ──
    try:
        # Send to primary (user's email)
        send_with_attachment(
            to=current_user.email,
            subject=f'Signed: {doc.filename}',
            text=f'Please find the signed version of {doc.filename} attached.\n\nSigned via WeScan.',
            pdf_bytes=signed_pdf_bytes,
            filename=f'signed-{doc.filename}'
        )

        # Send to additional recipients (no whitelisting needed — key selling point)
        for recipient_email in extra_recipients:
            try:
                send_with_attachment(
                    to=recipient_email,
                    subject=f'Signed: {doc.filename}',
                    text=f'Please find the signed version of {doc.filename} attached.\n\nSigned via WeScan.',
                    pdf_bytes=signed_pdf_bytes,
                    filename=f'signed-{doc.filename}'
                )
            except Exception as e:
                # Log but continue — don't fail the whole operation
                print(f'Failed to send to {recipient_email}: {e}')
    except Exception as e:
        return jsonify({'error': f'Failed to send email: {str(e)}'}), 500

    # ── Create SignedDocument record ──
    signed_doc = SignedDocument(
        user_id=current_user.id,
        document_id=doc.id,
        signature_id=signature.id,
        signature_x=sig_x,
        signature_y=sig_y,
        signature_page=sig_page,
        signed_file_data=signed_pdf_bytes,
        signed_file_size=len(signed_pdf_bytes),
        status='sent',
        sent_at=datetime.utcnow(),
        sent_to_primary=current_user.email,
        sent_to_additional=','.join(extra_recipients) if extra_recipients else None
    )
    db.session.add(signed_doc)

    # Mark document as signed
    doc.status = 'signed'
    doc.signed_at = datetime.utcnow()

    db.session.commit()

    return jsonify({'ok': True, 'signed_document_id': signed_doc.id})


# ── Signature Management ──

@dashboard.route('/dashboard/signatures', methods=['GET'])
@login_required
def list_signatures():
    sigs = Signature.query.filter_by(user_id=current_user.id).all()
    return jsonify([{
        'id': s.id,
        'name': s.name,
        'data': s.data,
        'created_at': s.created_at.isoformat()
    } for s in sigs])


@dashboard.route('/dashboard/signatures', methods=['POST'])
@login_required
def create_signature():
    limits = get_plan_limits(current_user)
    max_sigs = limits.get('max_signatures')
    if max_sigs is not None:
        count = Signature.query.filter_by(user_id=current_user.id).count()
        if count >= max_sigs:
            return jsonify({'error': f'Your plan allows up to {max_sigs} saved signature{"s" if max_sigs != 1 else ""}. Delete one to create another, or upgrade your plan.'}), 403

    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    sig_data = data.get('data', '').strip()  # base64 PNG

    if not name:
        return jsonify({'error': 'Signature name is required'}), 400
    if not sig_data:
        return jsonify({'error': 'Signature data is required'}), 400

    signature = Signature(
        user_id=current_user.id,
        name=name,
        data=sig_data
    )
    db.session.add(signature)
    db.session.commit()

    return jsonify({'ok': True, 'id': signature.id, 'name': signature.name}), 201


@dashboard.route('/dashboard/signatures/<int:sig_id>', methods=['DELETE'])
@login_required
def delete_signature(sig_id):
    sig = Signature.query.get_or_404(sig_id)
    if sig.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404
    db.session.delete(sig)
    db.session.commit()
    return jsonify({'ok': True})


# ── Enterprise Features: Protect, Watermark, Share ──────────────────────────

@dashboard.route('/dashboard/documents/<int:doc_id>/protect', methods=['POST'])
@login_required
def protect_document(doc_id):
    limits = get_plan_limits(current_user)
    if not limits['enterprise_features']:
        return jsonify({'error': 'Upgrade to Business or Enterprise for this feature.'}), 403

    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    password = (request.get_json(silent=True) or {}).get('password', '')
    if len(password) < 4:
        return jsonify({'error': 'Password must be at least 4 characters'}), 400

    from flask import send_file
    import fitz
    pdf = fitz.open(stream=doc.file_data, filetype='pdf')
    output = io.BytesIO()
    pdf.save(output, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, garbage=4, deflate=True)
    pdf.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'protected-{doc.filename}'
    )


@dashboard.route('/dashboard/documents/<int:doc_id>/watermark', methods=['POST'])
@login_required
def watermark_document(doc_id):
    limits = get_plan_limits(current_user)
    if not limits['enterprise_features']:
        return jsonify({'error': 'Upgrade to Business or Enterprise for this feature.'}), 403

    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or 'CONFIDENTIAL').strip()[:50]
    try:
        font_size = max(8, min(72, int(data.get('font_size', 36))))
    except (ValueError, TypeError):
        font_size = 36

    if not text:
        return jsonify({'error': 'Watermark text is required'}), 400

    from flask import send_file
    import fitz
    pdf = fitz.open(stream=doc.file_data, filetype='pdf')

    for page in pdf:
        rect = page.rect
        step_x = rect.width / 3
        step_y = rect.height / 3

        for row in range(4):
            for col in range(4):
                x = step_x * col - step_x * 0.3
                y = step_y * row
                if 0 <= x <= rect.width and 0 <= y <= rect.height:
                    page.insert_text(
                        fitz.Point(x, y + font_size),
                        text,
                        fontsize=font_size,
                        color=(0.8, 0.8, 0.8),
                        fontname='helv',
                        rotate=45
                    )

    output = io.BytesIO()
    pdf.save(output, garbage=4, deflate=True)
    pdf.close()
    output.seek(0)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'watermarked-{doc.filename}'
    )


@dashboard.route('/dashboard/documents/<int:doc_id>/share', methods=['POST'])
@login_required
def share_document(doc_id):
    limits = get_plan_limits(current_user)
    if not limits['enterprise_features']:
        return jsonify({'error': 'Upgrade to Business or Enterprise for this feature.'}), 403

    doc = Document.query.get_or_404(doc_id)
    if doc.user_id != current_user.id:
        return jsonify({'error': 'Not found'}), 404

    from app.models import SharedLink
    # Deactivate any existing active links for this document
    SharedLink.query.filter_by(document_id=doc.id, is_active=True).update({'is_active': False})

    import secrets
    token = secrets.token_urlsafe(24)
    link = SharedLink(
        token=token,
        document_id=doc.id,
        user_id=current_user.id,
        expires_at=datetime.utcnow() + timedelta(days=7)
    )
    db.session.add(link)
    db.session.commit()

    return jsonify({
        'ok': True,
        'url': f'https://wescan.net/share/{token}',
        'expires_at': link.expires_at.isoformat()
    })
