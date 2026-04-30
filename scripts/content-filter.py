#!/usr/bin/env python3
"""
WeScan content filter / relay script.
Called by Postfix as: content-filter.py {sasl_username} {recipient}
Reads the full email from stdin, validates against Flask API,
then delivers via Mailgun HTTP API (bypasses DO port 25 block).
"""
import sys
import os
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
    try:
        resp = requests.post(
            f'{FLASK_URL}/api/smtp/validate',
            json={'sender': sender, 'recipient': recipient},
            timeout=5
        )
        return resp.status_code == 200
    except Exception as e:
        sys.stderr.write(f'Validation error: {e}\n')
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

    # Ensure From: is a valid wescan.net address (Mailgun rejects sandbox/blank senders)
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
        sys.stderr.write('Usage: content-filter.py <sasl_username> <recipient>\n')
        sys.exit(1)

    sender    = sys.argv[1]
    recipient = sys.argv[2]

    # Read full email from stdin
    raw_message = sys.stdin.buffer.read()

    # 1. Validate recipient against whitelist
    if not validate(sender, recipient):
        sys.stderr.write(f'Rejected: {sender} ___ {recipient}\n')
        sys.exit(1)

    # 2. Send via Mailgun API
    env = get_env()
    if not send_via_mailgun(env, sender, recipient, raw_message):
        sys.stderr.write(f'Delivery failed: {sender} ___ {recipient}\n')
        sys.exit(1)

    sys.exit(0)
