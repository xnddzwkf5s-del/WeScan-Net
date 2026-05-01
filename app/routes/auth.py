from flask import Blueprint, redirect, url_for, request, jsonify, render_template_string, session
from flask_login import login_user, logout_user, login_required, current_user
from authlib.integrations.flask_client import OAuth
from app.models import db, User, OTPToken
from app.email import send_otp_email, send_welcome_email, send_admin_signup_notification
from datetime import datetime, timedelta
import os
import requests as http_requests


def _apply_trial_if_requested(user, plan):
    """If plan is enterprise-trial and user is new (free), grant 14-day trial."""
    if plan == 'enterprise-trial' and user.trial_end is None and user.plan == 'free':
        user.plan = 'enterprise'
        user.trial_end = datetime.utcnow() + timedelta(days=14)


def _expire_trial_if_due(user):
    """Downgrade user if trial has expired."""
    if user.trial_end and datetime.utcnow() > user.trial_end:
        user.plan = 'free'
        user.trial_end = None
        db.session.commit()


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
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        api_base_url='https://www.googleapis.com/oauth2/v1/',
        client_kwargs={'scope': 'openid email profile'}
    )

if os.getenv('MICROSOFT_CLIENT_ID'):
    oauth.register(
        name='microsoft',
        client_id=os.getenv('MICROSOFT_CLIENT_ID'),
        client_secret=os.getenv('MICROSOFT_CLIENT_SECRET'),
        access_token_url='https://login.microsoftonline.com/common/oauth2/v2.0/token',
        authorize_url='https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
        client_kwargs={'scope': 'User.Read openid email profile'}
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
    if not os.getenv(f'{provider.upper()}_CLIENT_ID'):
        return redirect('/signup.html?error=oauth_not_configured')
    session['signup_plan'] = request.args.get('plan', 'free')
    callback_url = url_for('auth.oauth_callback', provider=provider, _external=True)
    return oauth.create_client(provider).authorize_redirect(redirect_uri=callback_url)


@auth.route('/auth/callback/<provider>')
def oauth_callback(provider):
    plan = session.pop('signup_plan', 'free')
    if provider == 'microsoft':
        # Manual Microsoft OAuth: exchange code for token, then call Graph API
        code = request.args.get('code')
        token_resp = http_requests.post(
            'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            data={
                'client_id': os.getenv('MICROSOFT_CLIENT_ID'),
                'client_secret': os.getenv('MICROSOFT_CLIENT_SECRET'),
                'code': code,
                'redirect_uri': url_for('auth.oauth_callback', provider='microsoft', _external=True),
                'grant_type': 'authorization_code',
            },
            timeout=10
        )
        token_data = token_resp.json()
        access_token = token_data.get('access_token')
        if not access_token:
            return 'OAuth token exchange failed', 400

        graph_resp = http_requests.get(
            'https://graph.microsoft.com/v1.0/me',
            headers={'Authorization': f'Bearer {access_token}'},
            timeout=10
        )
        user_info = graph_resp.json()
        oauth_id = user_info.get('id')
        email = user_info.get('mail') or user_info.get('userPrincipalName') or ''
        name = user_info.get('displayName', email.split('@')[0])
    else:
        # Google uses authlib's built-in flow
        token = oauth.create_client(provider).authorize_access_token()
        resp = oauth.create_client(provider).get('userinfo')
        user_info = resp.json()
        oauth_id = user_info['id']
        email = user_info['email']
        name = user_info.get('name', email.split('@')[0])

    # Look up by OAuth ID first, then by email (handles existing email-signup users)
    user = User.query.filter_by(
        oauth_provider=provider,
        oauth_id=oauth_id
    ).first()

    if not user:
        # Check if email already exists (created via email signup)
        user = User.query.filter_by(email=email).first()
        if user:
            # Link OAuth to existing account
            user.oauth_provider = provider
            user.oauth_id = oauth_id
        else:
            # Brand new user via OAuth
            user = User(
                email=email,
                name=name,
                oauth_provider=provider,
                oauth_id=oauth_id,
                smtp_username=f"s_{os.urandom(6).hex()}",
                plan='free',
                inbox_address=User.generate_inbox_slug()
            )
            db.session.add(user)
            db.session.flush()
            _apply_trial_if_requested(user, plan)
            db.session.commit()
            try:
                send_welcome_email(user.email, user.smtp_username)
                send_admin_signup_notification(user.email, plan, signup_method='oauth')
            except Exception:
                pass
            login_user(user)
            return redirect(url_for('dashboard.index'))

    _expire_trial_if_due(user)
    db.session.commit()
    login_user(user)
    return redirect(url_for('dashboard.index'))


# ── Email OTP signup / sign-in ───────────────────────────────────────────────

@auth.route('/api/auth/signup', methods=['POST'])
def email_signup():
    email = request.form.get('email', '').strip().lower()
    plan = request.form.get('plan', 'free')
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

    return redirect(f'/verify.html?email={email}&plan={plan}')


@auth.route('/api/auth/verify', methods=['POST'])
def email_verify():
    email = request.form.get('email', '').strip().lower()
    code = request.form.get('code', '').strip()
    plan = request.form.get('plan', 'free')

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
            plan='free',
            inbox_address=User.generate_inbox_slug()
        )
        db.session.add(user)
        db.session.flush()
        _apply_trial_if_requested(user, plan)
        is_new_user = True
    else:
        _expire_trial_if_due(user)

    db.session.commit()
    login_user(user)

    if is_new_user:
        try:
            send_welcome_email(user.email, user.smtp_username)
            send_admin_signup_notification(user.email, plan, signup_method='email')
        except Exception:
            pass

    return redirect(url_for('dashboard.index'))


# ── Logout ───────────────────────────────────────────────────────────────────

@auth.route('/logout')
def logout():
    logout_user()
    return redirect('/')
