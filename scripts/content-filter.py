#!/usr/bin/env python3
import sys
import requests

def validate_email(sender, recipient):
    response = requests.post(
        'http://127.0.0.1:5000/api/smtp/validate',
        json={'sender': sender, 'recipient': recipient}
    )
    return response.status_code == 200

if __name__ == '__main__':
    sender = sys.argv[1]
    recipient = sys.argv[2]
    if not validate_email(sender, recipient):
        sys.exit(1)
    sys.exit(0)
