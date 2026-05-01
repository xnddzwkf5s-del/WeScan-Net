import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///wescan.db'
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
    STRIPE_PRICE_ID_PRO = os.environ.get('STRIPE_PRICE_ID_PRO', '')
    STRIPE_PRICE_ID_BUSINESS = os.environ.get('STRIPE_PRICE_ID_BUSINESS', '')
    STRIPE_PRICE_ID_ENTERPRISE = os.environ.get('STRIPE_PRICE_ID_ENTERPRISE', '')

    # Per-currency price IDs (set per plan in production)
    STRIPE_PRICE_PRO_AUD = os.environ.get('STRIPE_PRICE_PRO_AUD', '')
    STRIPE_PRICE_PRO_USD = os.environ.get('STRIPE_PRICE_PRO_USD', '')
    STRIPE_PRICE_PRO_EUR = os.environ.get('STRIPE_PRICE_PRO_EUR', '')
    STRIPE_PRICE_PRO_GBP = os.environ.get('STRIPE_PRICE_PRO_GBP', '')
    STRIPE_PRICE_BUS_AUD = os.environ.get('STRIPE_PRICE_BUS_AUD', '')
    STRIPE_PRICE_BUS_USD = os.environ.get('STRIPE_PRICE_BUS_USD', '')
    STRIPE_PRICE_BUS_EUR = os.environ.get('STRIPE_PRICE_BUS_EUR', '')
    STRIPE_PRICE_BUS_GBP = os.environ.get('STRIPE_PRICE_BUS_GBP', '')
    STRIPE_PRICE_ENT_AUD = os.environ.get('STRIPE_PRICE_ENT_AUD', '')
    STRIPE_PRICE_ENT_USD = os.environ.get('STRIPE_PRICE_ENT_USD', '')
    STRIPE_PRICE_ENT_EUR = os.environ.get('STRIPE_PRICE_ENT_EUR', '')
    STRIPE_PRICE_ENT_GBP = os.environ.get('STRIPE_PRICE_ENT_GBP', '')

    # SMTP relay (postfix integration)
    SMTP_RELAY_DOMAIN = 'wescan.net'
    SMTP_SERVER = 'smtp.wescan.net'
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
