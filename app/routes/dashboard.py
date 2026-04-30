from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, User, Recipient, UsageStat
import subprocess
import os
from werkzeug.security import generate_password_hash

dashboard = Blueprint('dashboard', __name__)

@dashboard.route('/dashboard')
@login_required
def index():
    recipients = Recipient.query.filter_by(user_id=current_user.id).all()
    usage = UsageStat.query.filter_by(user_id=current_user.id).order_by(UsageStat.sent_at.desc()).limit(10)

    return render_template('dashboard/index.html',
        user=current_user,
        recipients=recipients,
        usage=usage
    )

@dashboard.route('/dashboard/smtp/generate', methods=['POST'])
@login_required
def generate_smtp_password():
    password = os.urandom(12).hex()

    subprocess.run([
        'sudo',
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

    recipients = Recipient.query.filter_by(
        user_id=current_user.id
    ).all()

    return render_template('dashboard/recipients.html',
        recipients=recipients
    )

@dashboard.route('/dashboard/recipients/<int:id>/delete', methods=['POST'])
@login_required
def delete_recipient(id):
    recipient = Recipient.query.get_or_404(id)
    if recipient.user_id == current_user.id:
        db.session.delete(recipient)
        db.session.commit()
    return redirect(url_for('dashboard.manage_recipients'))
