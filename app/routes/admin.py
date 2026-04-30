from flask import Blueprint, render_template
from flask_login import login_required, current_user
from app.models import User, UsageStat
from datetime import datetime, timedelta

admin = Blueprint('admin', __name__)

@admin.route('/admin')
@login_required
def index():
    if not current_user.is_admin:
        return 'Unauthorized', 403

    users = User.query.all()
    stats = {
        'total_users': User.query.count(),
        'enterprise_users': User.query.filter_by(plan='enterprise').count(),
        'emails_today': UsageStat.query.filter(
            UsageStat.sent_at > datetime.utcnow() - timedelta(days=1)
        ).count()
    }

    return render_template('admin/index.html', users=users, stats=stats)
