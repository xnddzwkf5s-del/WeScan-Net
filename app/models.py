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
    inbox_address = db.Column(db.String(255), unique=True, nullable=True)

    @staticmethod
    def generate_inbox_slug():
        import secrets
        return 'i-' + secrets.token_hex(4)


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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    smtp_username = db.Column(db.String(50))
    attempted_recipient = db.Column(db.String(120))
    reason = db.Column(db.String(50), default='not_whitelisted')
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20))
    price = db.Column(db.Float)
    recipient_limit = db.Column(db.Integer)
    file_size_limit_mb = db.Column(db.Integer)


class Document(db.Model):
    __tablename__ = 'document'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    filename = db.Column(db.String(255), nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    mime_type = db.Column(db.String(50), default='application/pdf')
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    signed_at = db.Column(db.DateTime, nullable=True)
    user = db.relationship('User', backref=db.backref('documents', lazy='dynamic'))


class Signature(db.Model):
    __tablename__ = 'signature'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    data = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref=db.backref('signatures', lazy='dynamic'))


class SignedDocument(db.Model):
    __tablename__ = 'signed_document'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id', ondelete='SET NULL'), nullable=True)
    signature_id = db.Column(db.Integer, db.ForeignKey('signature.id', ondelete='SET NULL'), nullable=True)
    signature_x = db.Column(db.Float, default=0.5)
    signature_y = db.Column(db.Float, default=0.85)
    signature_page = db.Column(db.Integer, default=0)
    signed_file_data = db.Column(db.LargeBinary, nullable=True)
    signed_file_size = db.Column(db.Integer, nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime, nullable=True)
    sent_to_primary = db.Column(db.String(120), nullable=True)
    sent_to_additional = db.Column(db.String(500), nullable=True)
    user = db.relationship('User', backref=db.backref('sent_documents', lazy='dynamic'))
    document = db.relationship('Document', backref=db.backref('signed_versions', lazy='dynamic'))
    signature = db.relationship('Signature', backref=db.backref('used_in', lazy='dynamic'))


class SignaturePlacement(db.Model):
    """A single signature placement on a page within a signed document.
    One SignedDocument can have multiple placements (multi-signature, multi-page)."""
    __tablename__ = 'signature_placement'
    id = db.Column(db.Integer, primary_key=True)
    signed_document_id = db.Column(db.Integer, db.ForeignKey('signed_document.id'), nullable=False)
    signature_id = db.Column(db.Integer, db.ForeignKey('signature.id', ondelete='SET NULL'), nullable=True)
    page_num = db.Column(db.Integer, default=0)
    x = db.Column(db.Float, default=0.5)
    y = db.Column(db.Float, default=0.85)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    signed_document = db.relationship('SignedDocument', backref=db.backref('placement_records', lazy='dynamic', cascade='all, delete-orphan'))
    signature = db.relationship('Signature', backref=db.backref('via_placements', lazy='dynamic'))
