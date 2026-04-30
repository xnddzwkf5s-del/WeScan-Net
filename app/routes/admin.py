from flask import Blueprint, render_template, redirect, url_for, abort, flash
from flask_login import login_required, current_user
from app.models import db, User, UsageStat, Recipient, BlockedEmail
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
    now        = datetime.utcnow()
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d  = now - timedelta(days=7)
    cutoff_1d  = now - timedelta(days=1)

    # Per-user counts at multiple windows
    def user_counts(cutoff):
        return dict(
            db.session.query(UsageStat.user_id, func.count(UsageStat.id))
            .filter(UsageStat.sent_at > cutoff)
            .group_by(UsageStat.user_id)
            .all()
        )

    counts_30d = user_counts(cutoff_30d)
    counts_7d  = user_counts(cutoff_7d)
    counts_1d  = user_counts(cutoff_1d)

    # Active users = had at least one email in last 7 days
    active_user_ids = set(
        db.session.query(UsageStat.user_id)
        .filter(UsageStat.sent_at > cutoff_7d)
        .distinct()
        .all()
    )

    # Per-user blocked counts
    blocked_30d_by_user = dict(
        db.session.query(BlockedEmail.user_id, func.count(BlockedEmail.id))
        .filter(BlockedEmail.blocked_at > cutoff_30d, BlockedEmail.user_id.isnot(None))
        .group_by(BlockedEmail.user_id)
        .all()
    )

    # Recent blocked attempts per user (last 20 per user)
    blocked_recent_by_user = {}
    for row in (
        db.session.query(BlockedEmail)
        .filter(BlockedEmail.user_id.isnot(None), BlockedEmail.blocked_at > cutoff_30d)
        .order_by(BlockedEmail.blocked_at.desc())
        .all()
    ):
        blocked_recent_by_user.setdefault(row.user_id, []).append(row)

    users = User.query.order_by(User.created_at.desc()).all()
    for u in users:
        u.email_count_30d  = counts_30d.get(u.id, 0)
        u.email_count_7d   = counts_7d.get(u.id, 0)
        u.email_count_1d   = counts_1d.get(u.id, 0)
        u.recipients       = Recipient.query.filter_by(user_id=u.id, is_active=True).all()
        u.blocked_count_30d = blocked_30d_by_user.get(u.id, 0)
        u.blocked_emails   = blocked_recent_by_user.get(u.id, [])[:20]

    stats = {
        'total_users':      len(users),
        'free_users':       sum(1 for u in users if u.plan == 'free'),
        'enterprise_users': sum(1 for u in users if u.plan == 'enterprise'),
        'active_7d':        len(active_user_ids),
        'emails_today':     UsageStat.query.filter(UsageStat.sent_at > cutoff_1d).count(),
        'emails_30d':       UsageStat.query.filter(UsageStat.sent_at > cutoff_30d).count(),
        'total_recipients': Recipient.query.filter_by(is_active=True).count(),
        'smtp_active':      User.query.filter(User.smtp_password_hash.isnot(None)).count(),
        'blocked_today':    BlockedEmail.query.filter(BlockedEmail.blocked_at > cutoff_1d).count(),
        'blocked_30d':      BlockedEmail.query.filter(BlockedEmail.blocked_at > cutoff_30d).count(),
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
