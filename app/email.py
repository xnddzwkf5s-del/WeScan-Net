import os
import requests


def send_email(to, subject, text, html=None):
    """Send an email via Mailgun API."""
    api_key = os.getenv('MAILGUN_API_KEY')
    domain = os.getenv('MAILGUN_DOMAIN', 'wescan.net')

    if not api_key:
        raise RuntimeError('MAILGUN_API_KEY not set')

    data = {
        'from': f'WeScan <noreply@{domain}>',
        'to': [to],
        'subject': subject,
        'text': text,
    }
    if html:
        data['html'] = html

    resp = requests.post(
        f'https://api.mailgun.net/v3/{domain}/messages',
        auth=('api', api_key),
        data=data,
        timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def send_otp_email(to, otp):
    """Send OTP verification email."""
    subject = 'Your WeScan verification code'
    text = (
        f'Your WeScan verification code is: {otp}\n\n'
        f'This code expires in 10 minutes.\n\n'
        f'If you did not request this, please ignore this email.'
    )
    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:40px auto;padding:32px;border:1px solid #eee;border-radius:8px;">
      <h2 style="margin:0 0 24px;font-size:20px;">Verify your email</h2>
      <p style="color:#555;margin:0 0 24px;">Enter this code on the WeScan sign-up page:</p>
      <div style="font-size:36px;font-weight:700;letter-spacing:8px;text-align:center;padding:24px;background:#f9f9f9;border-radius:6px;margin:0 0 24px;">{otp}</div>
      <p style="color:#999;font-size:13px;margin:0;">This code expires in 10 minutes. If you didn't request this, ignore this email.</p>
    </div>
    """
    return send_email(to, subject, text, html)
