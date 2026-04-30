from flask import Blueprint, redirect, url_for, request, jsonify
from flask_login import login_user, logout_user, login_required
from authlib.integrations.flask_client import OAuth
from app.models import db, User, OTPToken
from app.email import send_otp_email
import os

auth = Blueprint('auth', __name__)
oauth = OAuth()

# OAuth configs
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    api_base_url='https://www.googleapis.com/oauth2/v1/',
    client_kwargs={'scope': 'openid email profile'}
)

@auth.route('/login/<provider>')
def oauth_login(provider):
    if provider not in ['google', 'microsoft', 'apple']:
        return 'Invalid OAuth provider', 400
    return oauth.create_client(provider).authorize_redirect(
        redirect_uri=url_for('auth.oauth_callback', provider=provider, _external=True)
    )

@auth.route('/auth/callback/<provider>')
def oauth_callback(provider):
    token = oauth.create_client(provider).authorize_access_token()
    resp = oauth.create_client(provider).get('userinfo')
    user_info = resp.json()

    user = User.query.filter_by(
        oauth_provider=provider,
        oauth_id=user_info['id']
    ).first()

    if not user:
        user = User(
            email=user_info['email'],
            name=user_info['name'],
            oauth_provider=provider,
            oauth_id=user_info['id'],
            smtp_username=f"s_{os.urandom(6).hex()}"
        )
        db.session.add(user)
        db.session.commit()

    login_user(user)
    return redirect(url_for('dashboard.index'))

@auth.route('/api/auth/signup', methods=['POST'])
def email_signup():
    email = request.form.get('email', '').strip().lower()
    if not email:
        return 'Email is required', 400

    # Invalidate any previous unused tokens for this email
    OTPToken.query.filter_by(email=email, used=False).delete()

    # Generate and store OTP
    token = OTPToken.generate(email)
    db.session.add(token)
    db.session.commit()

    # Send OTP email
    try:
        send_otp_email(email, token.code)
    except Exception as e:
        db.session.delete(token)
        db.session.commit()
        return jsonify({'error': f'Failed to send verification email: {str(e)}'}), 500

    # Redirect to verify page
    return redirect(f'/verify.html?email={email}')


@auth.route('/api/auth/verify', methods=['POST'])
def email_verify():
    email = request.form.get('email', '').strip().lower()
    code = request.form.get('code', '').strip()

    if not email or not code:
        return redirect(f'/verify.html?email={email}&error=missing')

    # Find latest valid token
    token = OTPToken.query.filter_by(email=email, used=False)\
        .order_by(OTPToken.created_at.desc()).first()

    if not token or not token.is_valid(code):
        return redirect(f'/verify.html?email={email}&error=invalid')

    # Mark token used
    token.used = True

    # Create or fetch user
    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            email=email,
            name=email.split('@')[0],
            smtp_username=f"s_{os.urandom(6).hex()}",
            plan='free'
        )
        db.session.add(user)

    db.session.commit()
    login_user(user)
    return redirect(url_for('dashboard.index'))

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))
