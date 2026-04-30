from flask import Blueprint, redirect, url_for, request
from flask_login import login_user, logout_user, login_required
from authlib.integrations.flask_client import OAuth
from app.models import db, User
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
