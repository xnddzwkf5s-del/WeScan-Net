from flask import Blueprint, redirect, url_for, request, jsonify, render_template_string
from flask_login import login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from app.models import db, User, OTPToken
from app.email import send_otp_email, send_welcome_email
import os
import requests as http_requests


def verify_turnstile(token):
    """Verify Cloudflare Turnstile response token."""
    secret = os.getenv('TURNSTILE_SECRET_KEY')
    if not secret:
        return True  # Skip if not configured
    resp = http_requests.post(
        'https://challenges.cloudflare.com/turnstile/v0/siteverify',
        data={'secret': secret, 'response': token},
        timeout=5
    )
    return resp.json().get('success', False)

auth = Blueprint('auth', __name__)
oauth = OAuth()

# OAuth configs (only register if keys present)
if os.getenv('GOOGLE_CLIENT_ID'):
    oauth.register(
        name='google',
        client_id=os.getenv('GOOGLE_CLIENT_ID'),
        client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
        access_token_url='https://accounts.google.com/o/oauth2/token',
        authorize_url='https://accounts.google.com/o/oauth2/auth',
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        client_kwargs={'scope': 'openid email profile'}
    )


def init_oauth(app):
    """Bind OAuth to the Flask app instance."""
    oauth.init_app(app)


# ── Login page (for returning email users) ──────────────────────────────────

@auth.route('/login')
def login_page():
    """Returning users land here — sends a fresh OTP."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    # Serve the signup page (it works for both new and returning users)
    return redirect('/signup.html')


# ── OAuth routes ─────────────────────────────────────────────────────────────

@auth.route('/login/<provider>')
def oauth_login(provider):
    if provider not in ['google', 'microsoft']:
        return 'Invalid OAuth provider', 400
    if not os.getenv('GOOGLE_CLIENT_ID'):
        return redirect('/signup.html?error=oauth_not_configured')
    return oauth.create_client(provider).authorize_redirect(
        redirect_uri=url_for('auth.oauth_callback', provider=provider, _external=True)
    )


@auth.route('/auth/callback/<provider>')
def oauth_callback(provider):
    token = oauth.create_client(provider).authorize_access_token()
    resp = oauth.create_client(provider).get('userinfo')
    user_info = resp.json()

    # Look up by OAuth ID first, then by email (handles existing email-signup users)
    user = User.query.filter_by(
        oauth_provider=provider,
        oauth_id=user_info['id']
    ).first()

    if not user:
        # Check if email already exists (created via email signup)
        user = User.query.filter_by(email=user_info['email']).first()
        if user:
            # Link OAuth to existing account
            user.oauth_provider = provider
            user.oauth_id = user_info['id']
        else:
            # Brand new user via OAuth
            user = User(
                email=user_info['email'],
                name=user_info.get('name', user_info['email'].split('@')[0]),
                oauth_provider=provider,
                oauth_id=user_info['id'],
                smtp_username=f"s_{os.urandom(6).hex()}",
                plan='free'
            )
            db.session.add(user)
            db.session.flush()  # get user.id before commit
            db.session.commit()
            try:
                send_welcome_email(user.email, user.smtp_username)
            except Exception:
                pass
            login_user(user)
            return redirect(url_for('dashboard.index'))

    db.session.commit()
    login_user(user)
    return redirect(url_for('dashboard.index'))


# ── Email OTP signup / sign-in ───────────────────────────────────────────────

@auth.route('/api/auth/signup', methods=['POST'])
def email_signup():
    # Turnstile verification
    turnstile_token = request.form.get('cf-turnstile-response', '')
    if not verify_turnstile(turnstile_token):
        return redirect('/signup.html?error=captcha_failed')

    email = request.form.get('email', '').strip().lower()
    if not email:
        return redirect('/signup.html?error=missing_email')

    # Invalidate previous unused tokens
    OTPToken.query.filter_by(email=email, used=False).delete()

    token = OTPToken.generate(email)
    db.session.add(token)
    db.session.commit()

    try:
        send_otp_email(email, token.code)
    except Exception as e:
        db.session.delete(token)
        db.session.commit()
        return redirect(f'/signup.html?error=email_failed')

    return redirect(f'/verify.html?email={email}')


@auth.route('/api/auth/verify', methods=['POST'])
def email_verify():
    # Turnstile verification
    turnstile_token = request.form.get('cf-turnstile-response', '')
    if not verify_turnstile(turnstile_token):
        return redirect(f'/verify.html?email={request.form.get("email","")}&error=captcha_failed')

    email = request.form.get('email', '').strip().lower()
    code = request.form.get('code', '').strip()

    if not email or not code:
        return redirect(f'/verify.html?email={email}&error=missing')

    token = OTPToken.query.filter_by(email=email, used=False)\
        .order_by(OTPToken.created_at.desc()).first()

    if not token or not token.is_valid(code):
        return redirect(f'/verify.html?email={email}&error=invalid')

    token.used = True

    is_new_user = False
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            email=email,
            name=email.split('@')[0],
            smtp_username=f"s_{os.urandom(6).hex()}",
            plan='free'
        )
        db.session.add(user)
        is_new_user = True

    db.session.commit()
    login_user(user)

    if is_new_user:
        try:
            send_welcome_email(user.email, user.smtp_username)
        except Exception:
            pass  # Don't block login if welcome email fails

    return redirect(url_for('dashboard.index'))


# ── Logout ───────────────────────────────────────────────────────────────────

@auth.route('/logout')
def logout():
    logout_user()
    return redirect('/')
