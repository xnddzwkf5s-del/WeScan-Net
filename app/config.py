import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///scanner2email.db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # OAuth
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    MICROSOFT_CLIENT_ID = os.environ.get('MICROSOFT_CLIENT_ID', '')
    MICROSOFT_CLIENT_SECRET = os.environ.get('MICROSOFT_CLIENT_SECRET', '')
    APPLE_CLIENT_ID = os.environ.get('APPLE_CLIENT_ID', '')

    # Stripe
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', '')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
    STRIPE_PRICE_ID_FREE = os.environ.get('STRIPE_PRICE_ID_FREE', '')
    STRIPE_PRICE_ID_ENTERPRISE = os.environ.get('STRIPE_PRICE_ID_ENTERPRISE', '')

    # SMTP relay (postfix integration)
    SMTP_RELAY_DOMAIN = 'scanner2mail.com'
    SMTP_SERVER = 'smtp.scanner2mail.com'
    SMTP_PORT = 587

    # Limits
    FREE_RECIPIENT_LIMIT = 15
    FREE_FILE_SIZE_MB = 10
    ENTERPRISE_RECIPIENT_LIMIT = 100
    ENTERPRISE_FILE_SIZE_MB = 25

    # Rate limiting
    RATE_LIMIT_PER_HOUR = 50

    # Session
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
