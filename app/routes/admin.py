from flask import Blueprint, render_template, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from app.models import db, User, UsageStat, Recipient
from datetime import datetime, timedelta
from sqlalchemy import func

admin = Blueprint('admin', __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin.route('/admin')
@login_required
@admin_required
def index():
    cutoff_30d = datetime.utcnow() - timedelta(days=30)
    cutoff_1d  = datetime.utcnow() - timedelta(days=1)

    # Per-user 30-day email counts in one query
    counts = dict(
        db.session.query(UsageStat.user_id, func.count(UsageStat.id))
        .filter(UsageStat.sent_at > cutoff_30d)
        .group_by(UsageStat.user_id)
        .all()
    )

    # Attach derived fields to each user
    users = User.query.order_by(User.created_at.desc()).all()
    for u in users:
        u.email_count_30d = counts.get(u.id, 0)
        u.recipients = Recipient.query.filter_by(user_id=u.id, is_active=True).all()

    stats = {
        'total_users':      len(users),
        'enterprise_users': sum(1 for u in users if u.plan == 'enterprise'),
        'emails_today':     UsageStat.query.filter(UsageStat.sent_at > cutoff_1d).count(),
        'total_recipients': Recipient.query.filter_by(is_active=True).count(),
    }

    return render_template('admin/index.html', users=users, stats=stats)


@admin.route('/admin/users/<int:user_id>/toggle-plan', methods=['POST'])
@login_required
@admin_required
def toggle_plan(user_id):
    user = User.query.get_or_404(user_id)
    user.plan = 'enterprise' if user.plan == 'free' else 'free'
    db.session.commit()
    flash(f'{user.email} moved to {user.plan} plan.', 'success')
    return redirect(url_for('admin.index'))


@admin.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot delete admin accounts.', 'error')
        return redirect(url_for('admin.index'))
    email = user.email
    Recipient.query.filter_by(user_id=user.id).delete()
    UsageStat.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'{email} deleted.', 'success')
    return redirect(url_for('admin.index'))
