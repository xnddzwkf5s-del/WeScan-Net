from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import db, User, Recipient, UsageStat, BlockedEmail
from datetime import datetime, timedelta
import subprocess
import os
from werkzeug.security import generate_password_hash

dashboard = Blueprint('dashboard', __name__)

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

    stats = {
        'emails_today':    UsageStat.query.filter_by(user_id=current_user.id)
                            .filter(UsageStat.sent_at > cutoff_1d).count(),
        'emails_7d':       UsageStat.query.filter_by(user_id=current_user.id)
                            .filter(UsageStat.sent_at > cutoff_7d).count(),
        'emails_30d':      UsageStat.query.filter_by(user_id=current_user.id)
                            .filter(UsageStat.sent_at > cutoff_30d).count(),
        'emails_total':    UsageStat.query.filter_by(user_id=current_user.id).count(),
        'blocked_today':   BlockedEmail.query.filter_by(user_id=current_user.id)
                            .filter(BlockedEmail.blocked_at > cutoff_1d).count(),
        'blocked_30d':     BlockedEmail.query.filter_by(user_id=current_user.id)
                            .filter(BlockedEmail.blocked_at > cutoff_30d).count(),
        'recipient_limit': 100 if current_user.plan == 'enterprise' else 5,
    }

    blocked_recent = BlockedEmail.query\
        .filter_by(user_id=current_user.id)\
        .filter(BlockedEmail.blocked_at > cutoff_30d)\
        .order_by(BlockedEmail.blocked_at.desc()).limit(10).all()

    # Trial / cancellation state
    trial_days_left = None
    trial_expired = False
    cancelling = False  # paid sub cancelled, still active until period end
    if current_user.trial_end:
        delta = (current_user.trial_end - now).days
        if delta >= 0:
            # Distinguish: has stripe_subscription_id = cancelling paid sub, else = trial
            if current_user.stripe_subscription_id:
                cancelling = True
                trial_days_left = delta
            else:
                trial_days_left = delta
        else:
            trial_expired = True

    return render_template('dashboard/index.html',
        user=current_user,
        recipients=recipients,
        usage=usage,
        stats=stats,
        blocked_recent=blocked_recent,
        trial_days_left=trial_days_left,
        trial_expired=trial_expired,
        cancelling=cancelling
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

        limit = 100 if current_user.plan == 'enterprise' else 15
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
