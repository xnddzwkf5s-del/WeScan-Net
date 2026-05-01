#!/usr/bin/env python3
"""Backfill inbox_address for existing users who don't have one."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    users = User.query.filter_by(inbox_address=None).all()
    count = 0
    for u in users:
        slug = User.generate_inbox_slug()
        # Ensure uniqueness (extremely unlikely collision, but be safe)
        while User.query.filter_by(inbox_address=slug).first():
            slug = User.generate_inbox_slug()
        u.inbox_address = slug
        count += 1
    db.session.commit()
    print(f'Backfilled inbox_address for {count} users.')
