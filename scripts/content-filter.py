#!/usr/bin/env python3
"""
WeScan content filter / relay script.
Called by Postfix as: content-filter.py {sasl_username|->} {recipient}
Reads the full email from stdin, validates against Flask API,
then delivers via Mailgun HTTP API (bypasses DO port 25 block).
When sasl_username is "-", treats as inbound inbox mail for i-xxxx@inbox.wescan.net.
"""
import sys
import os
import base64
import email as emaillib
import requests

FLASK_URL   = 'http://127.0.0.1:5000'
MAILGUN_API = 'https://api.mailgun.net/v3'


def get_env():
    env = {}
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def validate(sender, recipient):
    """Returns user_id on success, None on failure."""
    try:
        resp = requests.post(
            f'{FLASK_URL}/api/smtp/validate',
            json={'sender': sender, 'recipient': recipient},
            timeout=5
        )
        if resp.status_code == 200:
            return resp.json().get('user_id')
        return None
    except Exception as e:
        sys.stderr.write(f'Validation error: {e}\n')
        return None


def record_sent(user_id, recipient, file_size_bytes):
    """Record a successful delivery in the Flask DB."""
    try:
        requests.post(
            f'{FLASK_URL}/api/smtp/record',
            json={'user_id': user_id, 'recipient': recipient, 'file_size_bytes': file_size_bytes},
            timeout=5
        )
    except Exception as e:
        sys.stderr.write(f'Record error (non-fatal): {e}\n')


def process_inbox_email(recipient, raw_message):
    """Handle email sent to a user's inbox address (i-xxxx@inbox.wescan.net).
    Extracts and stores the PDF — no forwarding."""
    local_part = recipient.split('@')[0] if '@' in recipient else ''
    if not local_part.startswith('i-'):
        sys.stderr.write(f'Invalid inbox address format: {recipient}\n')
        return False
    try:
        email_b64 = base64.b64encode(raw_message).decode('ascii')
        resp = requests.post(
            f'{FLASK_URL}/api/documents/inbox-store',
            json={'inbox_address': local_part, 'email_data': email_b64},
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            docs = data.get('documents')
            if docs:
                for d in docs:
                    sys.stderr.write(f'Inbox doc stored: id={d.get("document_id")} filename={d.get("filename")}\n')
            else:
                sys.stderr.write(f'Inbox doc stored: id={data.get("document_id")} filename={data.get("filename")}\n')
            return True
        sys.stderr.write(f'Inbox store error {resp.status_code}: {resp.text[:200]}\n')
        return False
    except Exception as e:
        sys.stderr.write(f'Inbox store exception: {e}\n')
        return False


def store_document(smtp_username, recipient, raw_message):
    """Store the email as a Document in the Flask DB inbox.
    Returns True on success, False on failure."""
    try:
        email_b64 = base64.b64encode(raw_message).decode('ascii')
        resp = requests.post(
            f'{FLASK_URL}/api/documents/store',
            json={
                'smtp_username': smtp_username,
                'recipient': recipient,
                'email_data': email_b64
            },
            timeout=15
        )
        if resp.status_code == 200:
            data = resp.json()
            sys.stderr.write(f'Document stored: id={data.get("document_id")} filename={data.get("filename")}\n')
            return True
        else:
            sys.stderr.write(f'Store document error {resp.status_code}: {resp.text[:200]}\n')
            return False
    except Exception as e:
        sys.stderr.write(f'Store document exception: {e}\n')
        return False


def fix_from_header(raw_message, sender, domain):
    """
    Rewrite the From: header to a valid @domain address.
    Printers often send a blank From: or one Postfix substitutes with
    a Mailgun sandbox address — both get rejected by Mailgun.
    """
    try:
        msg = emaillib.message_from_bytes(raw_message)
        from_addr = msg.get('From', '')
        if not from_addr or domain not in from_addr:
            smtp_user = sender.split('@')[0] if '@' in sender else sender
            new_from  = f'{smtp_user}@{domain}'
            if 'From' in msg:
                del msg['From']
            msg['From'] = new_from
        return msg.as_bytes()
    except Exception as e:
        sys.stderr.write(f'From header rewrite warning: {e}\n')
        return raw_message


def send_via_mailgun(env, sender, recipient, raw_message):
    api_key = env.get('MAILGUN_API_KEY', '')
    domain  = env.get('MAILGUN_DOMAIN', 'wescan.net')
    if not api_key:
        sys.stderr.write('MAILGUN_API_KEY not set\n')
        return False

    raw_message = fix_from_header(raw_message, sender, domain)

    try:
        resp = requests.post(
            f'{MAILGUN_API}/{domain}/messages.mime',
            auth=('api', api_key),
            data={'to': recipient},
            files={'message': ('message.mime', raw_message, 'message/rfc822')},
            timeout=30
        )
        if resp.status_code == 200:
            return True
        sys.stderr.write(f'Mailgun error {resp.status_code}: {resp.text[:200]}\n')
        return False
    except Exception as e:
        sys.stderr.write(f'Mailgun send error: {e}\n')
        return False


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.stderr.write('Usage: content-filter.py <sasl_username|-> <recipient>\n')
        sys.exit(1)

    sasl_user  = sys.argv[1]
    recipient  = sys.argv[2]
    raw_message = sys.stdin.buffer.read()

    # INBOX FLOW: unauthenticated mail arriving for i-xxxx@inbox.wescan.net
    if sasl_user == "-" or sasl_user == "":
        result = process_inbox_email(recipient, raw_message)
        sys.exit(0 if result else 1)

    # EXISTING AUTHENTICATED SMTP FLOW (unchanged)
    user_id = validate(sasl_user, recipient)
    if not user_id:
        sys.stderr.write(f'Rejected: {sasl_user} ___ {recipient}\n')
        sys.exit(1)

    env = get_env()
    document_storage_mode = env.get('DOCUMENT_STORAGE_MODE', '').lower() == 'true'

    if document_storage_mode:
        if not store_document(sasl_user, recipient, raw_message):
            sys.stderr.write(f'Document storage failed: {sasl_user} ___ {recipient}\n')
            if not send_via_mailgun(env, sasl_user, recipient, raw_message):
                sys.stderr.write(f'Delivery failed: {sasl_user} ___ {recipient}\n')
                sys.exit(1)
            record_sent(user_id, recipient, len(raw_message))
    else:
        if not send_via_mailgun(env, sasl_user, recipient, raw_message):
            sys.stderr.write(f'Delivery failed: {sasl_user} ___ {recipient}\n')
            sys.exit(1)
        record_sent(user_id, recipient, len(raw_message))

    sys.exit(0)
