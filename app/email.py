import os
import requests


def send_email(to, subject, text, html=None):
    """Send an email via Mailgun API."""
    api_key = os.getenv('MAILGUN_API_KEY')
    domain  = os.getenv('MAILGUN_DOMAIN', 'wescan.net')

    if not api_key:
        raise RuntimeError('MAILGUN_API_KEY not set')

    data = {
        'from': f'WeScan <noreply@{domain}>',
        'to':   [to],
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


def send_with_attachment(to, subject, text, pdf_bytes, filename='signed-document.pdf'):
    """Send email with PDF attachment via Mailgun."""
    api_key = os.getenv('MAILGUN_API_KEY')
    domain  = os.getenv('MAILGUN_DOMAIN', 'wescan.net')

    if not api_key:
        raise RuntimeError('MAILGUN_API_KEY not set')

    data = {
        'from': f'WeScan <noreply@{domain}>',
        'to':   [to],
        'subject': subject,
        'text': text,
    }

    files = [
        ('attachment', (filename, pdf_bytes, 'application/pdf'))
    ]

    resp = requests.post(
        f'https://api.mailgun.net/v3/{domain}/messages',
        auth=('api', api_key),
        data=data,
        files=files,
        timeout=30
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


def send_welcome_email(to, smtp_username, inbox_address=None):
    """Send welcome email highlighting PDF signing + inbox address."""
    domain        = os.getenv('MAILGUN_DOMAIN', 'wescan.net')
    smtp_server   = f'smtp.{domain}'
    dashboard_url = f'https://{domain}/dashboard'
    inbox_full    = f'{inbox_address}@inbox.{domain}' if inbox_address else f'your-inbox@inbox.{domain}'

    subject = 'Welcome to WeScan — sign your first document'

    text = f"""\
Welcome to WeScan!

Your account is ready. Here's how to sign your first document.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR DOCUMENT INBOX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{inbox_full}

This is your personal inbox address. Email any PDF to this
address and it will appear in your dashboard ready to sign.
You can also upload PDFs directly from the dashboard.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SIGN YOUR FIRST DOCUMENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Go to your dashboard: {dashboard_url}
2. Upload a PDF or email one to {inbox_full}
3. Click the document → Sign
4. Draw your signature and position it on the page
5. Click "Send Signed Document"

The signed PDF is emailed to your recipient automatically.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOR SCANNER / PRINTER USERS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WeScan also works as a Scan-to-Email relay.
SMTP Server : {smtp_server}
Port        : 587
Security    : STARTTLS
Username    : {smtp_username}
Password    : Generate in your dashboard under Settings

Scanned documents will appear in your dashboard for signing.
Setup guides: https://{domain}/setup-guide.html

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NEED HELP?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Email us at support@wescan.net — we reply fast.

— The WeScan Team
https://wescan.net
"""

    html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;max-width:560px;width:100%;">

      <!-- Header -->
      <tr>
        <td style="background:#000000;padding:28px 40px;">
          <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">
            We<span style="color:#888888;">Scan</span>
          </span>
        </td>
      </tr>

      <!-- Hero -->
      <tr>
        <td style="padding:40px 40px 24px;">
          <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#111;">Your account is ready. ✍️</h1>
          <p style="margin:0;color:#555;font-size:15px;line-height:1.6;">
            Sign, send and receive documents — all from your browser or phone.
            Here's everything you need to get started.
          </p>
        </td>
      </tr>

      <!-- Inbox address box -->
      <tr>
        <td style="padding:0 40px 32px;">
          <div style="background:#f9f9f9;border:1px solid #e8e8e8;border-radius:8px;padding:24px;">
            <p style="margin:0 0 6px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#999;">Your Document Inbox</p>
            <p style="margin:0 0 12px;font-size:18px;font-weight:700;color:#111;font-family:monospace;word-break:break-all;">{inbox_full}</p>
            <p style="margin:0;font-size:13px;color:#666;line-height:1.6;">
              Email any PDF to this address and it will appear in your dashboard, ready to sign.
              You can also upload PDFs directly from the dashboard.
            </p>
          </div>
        </td>
      </tr>

      <!-- Steps -->
      <tr>
        <td style="padding:0 40px 12px;">
          <p style="margin:0 0 20px;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#999;">How to sign a document</p>

          <!-- Step 1 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 20px;width:100%;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;width:36px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">1</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Get your document into WeScan</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  Upload a PDF from the <a href="{dashboard_url}" style="color:#000;font-weight:600;">dashboard</a>,
                  or email it directly to <span style="font-family:monospace;font-weight:600;color:#111;">{inbox_full}</span>.
                  It will appear under <strong>Documents</strong> automatically.
                </p>
              </td>
            </tr>
          </table>

          <!-- Step 2 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 20px;width:100%;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;width:36px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">2</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Create your signature</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  Go to the <strong>Sign</strong> page for any document.
                  Draw your signature with your mouse or finger, give it a name, and save.
                  You can reuse it on any future document.
                </p>
              </td>
            </tr>
          </table>

          <!-- Step 3 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 20px;width:100%;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;width:36px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">3</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Position and send</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  Drag your signature to the right spot on the page, click
                  <strong>Sign on This Page</strong>, then hit <strong>Send Signed Document</strong>.
                  The signed PDF is emailed to your recipient automatically.
                </p>
              </td>
            </tr>
          </table>

          <!-- Step 4 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 32px;width:100%;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;width:36px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">4</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Add recipients</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  WeScan delivers signed documents only to addresses you've pre-approved.
                  Go to <strong>Recipients</strong> in the dashboard and add the emails
                  you want to send to. Free plan allows up to 5.
                </p>
              </td>
            </tr>
          </table>

        </td>
      </tr>

      <!-- CTA -->
      <tr>
        <td style="padding:0 40px 32px;">
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="background:#000;border-radius:6px;padding:14px 28px;">
                <a href="{dashboard_url}" style="color:#fff;font-size:14px;font-weight:600;text-decoration:none;display:block;">Go to Dashboard →</a>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Scanner section -->
      <tr>
        <td style="padding:0 40px 32px;">
          <div style="border-top:1px solid #eee;padding-top:28px;">
            <p style="margin:0 0 10px;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#999;">Have a scanner or printer?</p>
            <p style="margin:0 0 16px;font-size:14px;color:#555;line-height:1.6;">
              WeScan also works as a Scan-to-Email relay. Enter these credentials in your device’s
              “Scan to Email” settings and scanned documents will land in your dashboard automatically.
            </p>
            <table cellpadding="0" cellspacing="0" style="width:100%;font-size:13px;background:#f9f9f9;border:1px solid #e8e8e8;border-radius:6px;padding:16px;">
              <tr>
                <td style="color:#888;padding:4px 0;width:110px;">SMTP Server</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">{smtp_server}</td>
              </tr>
              <tr>
                <td style="color:#888;padding:4px 0;">Port</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">587 (STARTTLS)</td>
              </tr>
              <tr>
                <td style="color:#888;padding:4px 0;">Username</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">{smtp_username}</td>
              </tr>
              <tr>
                <td style="color:#888;padding:4px 0;">Password</td>
                <td style="color:#555;font-style:italic;">Generate in dashboard → Settings</td>
              </tr>
            </table>
            <p style="margin:12px 0 0;font-size:13px;color:#888;">
              Setup guides for HP, Canon, Epson &amp; Brother:
              <a href="https://{domain}/setup-guide.html" style="color:#000;font-weight:600;">wescan.net/setup-guide.html</a>
            </p>
          </div>
        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9f9f9;padding:20px 40px;border-top:1px solid #eee;">
          <p style="margin:0;font-size:12px;color:#aaa;line-height:1.8;">
            Questions? Email us at <a href="mailto:support@wescan.net" style="color:#888;">support@wescan.net</a><br>
            You’re receiving this because you signed up at wescan.net.<br>
            © 2026 WeScan. All rights reserved.
          </p>
        </td>
      </tr>

    </table>
  </td></tr>
</table>
</body>
</html>
"""

    return send_email(to, subject, text, html)


def send_admin_signup_notification(user_email, plan='free', signup_method='email'):
    """Notify admin (Vincent) when a new user signs up."""
    admin_email = os.getenv('ADMIN_EMAIL', 'vwoo@outlook.com.au')
    from datetime import datetime
    iso_time = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')

    subject = f'🔔 New WeScan signup: {user_email}'
    text = (
        f'New user signed up on wescan.net\n'
        f'Email: {user_email}\n'
        f'Plan: {plan}\n'
        f'Method: {signup_method}\n'
        f'Time: {iso_time}\n'
    )

    return send_email(admin_email, subject, text)
