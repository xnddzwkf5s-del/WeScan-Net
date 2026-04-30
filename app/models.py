from app import db
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120))
    oauth_provider = db.Column(db.String(20))
    oauth_id = db.Column(db.String(100))
    smtp_username = db.Column(db.String(50), unique=True)
    smtp_password_hash = db.Column(db.String(200))
    plan = db.Column(db.String(20), default='free')
    stripe_customer_id = db.Column(db.String(100))
    stripe_subscription_id = db.Column(db.String(100))
    trial_end = db.Column(db.DateTime, nullable=True)
    verify_requested_at = db.Column(db.DateTime, nullable=True)
    scan_verified_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Recipient(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    display_name = db.Column(db.String(120))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class UsageStat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_email = db.Column(db.String(120))
    file_type = db.Column(db.String(10))
    file_size_bytes = db.Column(db.Integer)
    status = db.Column(db.String(20))
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)

class OTPToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False, index=True)
    code = db.Column(db.String(6), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @staticmethod
    def generate(email):
        code = ''.join(random.choices(string.digits, k=6))
        expires = datetime.utcnow() + timedelta(minutes=10)
        token = OTPToken(email=email, code=code, expires_at=expires)
        return token

    def is_valid(self, code):
        return (
            not self.used and
            self.code == code and
            datetime.utcnow() < self.expires_at
        )

class BlockedEmail(db.Model):
    """Lightweight record of a blocked/rejected delivery attempt.
    No email content is stored — only metadata for admin stats."""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # null if unknown sender
    smtp_username = db.Column(db.String(50))   # who tried to send
    attempted_recipient = db.Column(db.String(120))  # where they tried to send
    reason = db.Column(db.String(50), default='not_whitelisted')  # not_whitelisted | unknown_user
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20))
    price = db.Column(db.Float)
    recipient_limit = db.Column(db.Integer)
    file_size_limit_mb = db.Column(db.Integer)
