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


def send_welcome_email(to, smtp_username):
    """Send welcome + SMTP setup instructions to a newly registered user."""
    domain        = os.getenv('MAILGUN_DOMAIN', 'wescan.net')
    smtp_server   = f'smtp.{domain}'
    dashboard_url = f'https://{domain}/dashboard'

    subject = 'Welcome to WeScan — your setup guide'

    text = f"""\
Welcome to WeScan!

Your account is ready. Here's everything you need to start scanning to email.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR SMTP CREDENTIALS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SMTP Server : {smtp_server}
Port        : 587
Security    : STARTTLS
Username    : {smtp_username}
Password    : (generate one in your dashboard — see below)

HOW TO GET YOUR SMTP PASSWORD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Sign in at {dashboard_url}
2. Go to the "SMTP Password" section
3. Click "Generate Password"
4. Copy the password — it will only be shown once

Enter these details into your scanner or printer under
"Scan to Email" or "Email Settings".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IMPORTANT: WHITELIST YOUR RECIPIENTS FIRST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WeScan will ONLY deliver scans to email addresses you have
pre-approved. Emails sent to any other address will be
blocked — no exceptions.

To whitelist a recipient:
1. Sign in at {dashboard_url}
2. Go to the "Recipients" section
3. Click "Add Recipient" and enter the email address
4. That address can now receive your scans

Free plan allows up to 5 whitelisted recipients.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUICK SETUP SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. Add your recipient emails in the dashboard
2. Generate your SMTP password
3. Enter SMTP settings on your scanner
4. Send a test scan

Full setup guides for HP, Canon, Epson and Brother at:
https://{domain}/setup-guide.html

If you need help, reply to this email.

— The WeScan Team
"""

    html = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#f5f5f5;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:40px 0;">
  <tr><td align="center">
    <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">

      <!-- Header -->
      <tr>
        <td style="background:#000000;padding:28px 40px;">
          <span style="font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.5px;">
            We<span style="color:#888888;">Scan</span>
          </span>
        </td>
      </tr>

      <!-- Body -->
      <tr>
        <td style="padding:40px;">

          <h1 style="margin:0 0 8px;font-size:24px;font-weight:700;color:#111;">
            You're all set.
          </h1>
          <p style="margin:0 0 32px;color:#555;font-size:15px;line-height:1.6;">
            Your WeScan account is ready. Follow the steps below to get your scanner sending emails in minutes.
          </p>

          <!-- SMTP Credentials box -->
          <div style="background:#f9f9f9;border:1px solid #e8e8e8;border-radius:6px;padding:24px;margin:0 0 32px;">
            <p style="margin:0 0 16px;font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:1px;color:#999;">
              Your SMTP Credentials
            </p>
            <table cellpadding="0" cellspacing="0" style="width:100%;font-size:14px;">
              <tr>
                <td style="color:#888;padding:5px 0;width:130px;">SMTP Server</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">{smtp_server}</td>
              </tr>
              <tr>
                <td style="color:#888;padding:5px 0;">Port</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">587</td>
              </tr>
              <tr>
                <td style="color:#888;padding:5px 0;">Security</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">STARTTLS</td>
              </tr>
              <tr>
                <td style="color:#888;padding:5px 0;">Username</td>
                <td style="color:#111;font-weight:600;font-family:monospace;">{smtp_username}</td>
              </tr>
              <tr>
                <td style="color:#888;padding:5px 0;">Password</td>
                <td style="color:#555;font-style:italic;">Generate in your dashboard →</td>
              </tr>
            </table>
          </div>

          <!-- Step 1 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">1</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Whitelist your recipients</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  WeScan only delivers to pre-approved addresses.
                  Sign in to your <a href="{dashboard_url}" style="color:#000;font-weight:600;">dashboard</a>,
                  go to <strong>Recipients</strong>, and add every email address
                  you want to scan to. Scans sent to any other address will be <strong>blocked</strong>.
                </p>
              </td>
            </tr>
          </table>

          <!-- Step 2 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 20px;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">2</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Generate your SMTP password</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  In your dashboard go to <strong>Settings → SMTP Password</strong> and click
                  <strong>Generate Password</strong>. Save it — it's only shown once.
                </p>
              </td>
            </tr>
          </table>

          <!-- Step 3 -->
          <table cellpadding="0" cellspacing="0" style="margin:0 0 32px;">
            <tr>
              <td style="vertical-align:top;padding-right:16px;">
                <div style="width:28px;height:28px;background:#000;border-radius:50%;text-align:center;line-height:28px;font-size:13px;font-weight:700;color:#fff;">3</div>
              </td>
              <td style="vertical-align:top;">
                <p style="margin:3px 0 4px;font-size:15px;font-weight:600;color:#111;">Configure your scanner</p>
                <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">
                  Enter the SMTP credentials above into your scanner's
                  "Scan to Email" or "Email Settings" menu.
                  See the <a href="https://{domain}/setup-guide.html" style="color:#000;font-weight:600;">setup guide</a>
                  for step-by-step instructions for HP, Canon, Epson, and Brother.
                </p>
              </td>
            </tr>
          </table>

          <!-- Warning banner -->
          <div style="background:#fffbeb;border:1px solid #f5e27a;border-radius:6px;padding:16px 20px;margin:0 0 32px;">
            <p style="margin:0;font-size:13px;color:#7a5c00;line-height:1.6;">
              <strong>⚠️ Recipients must be whitelisted before scanning.</strong>
              Scans to non-whitelisted addresses are silently blocked and cannot be recovered.
              Free plan: up to 5 recipients. <a href="https://{domain}/#pricing" style="color:#7a5c00;">Upgrade</a> for more.
            </p>
          </div>

          <!-- CTA -->
          <table cellpadding="0" cellspacing="0">
            <tr>
              <td style="background:#000;border-radius:6px;padding:14px 28px;">
                <a href="{dashboard_url}" style="color:#fff;font-size:14px;font-weight:600;text-decoration:none;display:block;">
                  Go to Dashboard →
                </a>
              </td>
            </tr>
          </table>

        </td>
      </tr>

      <!-- Footer -->
      <tr>
        <td style="background:#f9f9f9;padding:20px 40px;border-top:1px solid #eee;">
          <p style="margin:0;font-size:12px;color:#aaa;line-height:1.6;">
            You're receiving this because you signed up at wescan.net.<br>
            Questions? Reply to this email.<br>
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
