#!/usr/bin/env python3
"""
CLI tool to manage Scanner2Email users, recipients, and SMTP credentials.
Run on the server after deployment.
"""
import sys
import argparse
import sqlite3
import secrets
from werkzeug.security import generate_password_hash

DB_PATH = '/opt/wescan/instance/wescan.db'


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def list_users():
    conn = get_db()
    rows = conn.execute('SELECT id, email, name, plan, is_active FROM user ORDER BY created_at DESC').fetchall()
    print(f"{'ID':<8} {'Email':<35} {'Name':<20} {'Plan':<12} {'Active'}")
    print("-" * 80)
    for r in rows:
        print(f"{r['id'][:8]:<8} {r['email']:<35} {r['name'] or '-':<20} {r['plan']:<12} {r['is_active']}")
    conn.close()


def set_plan(user_id, plan):
    conn = get_db()
    conn.execute('UPDATE user SET plan = ? WHERE id = ?', (plan, user_id))
    conn.commit()
    print(f"User {user_id[:8]} set to {plan} plan")
    conn.close()


def set_admin(user_id):
    conn = get_db()
    conn.execute('UPDATE user SET is_admin = 1 WHERE id = ?', (user_id,))
    conn.commit()
    print(f"User {user_id[:8]} promoted to admin")
    conn.close()


def generate_smtp(user_id):
    conn = get_db()
    password = secrets.token_urlsafe(16)
    hashed = generate_password_hash(password)
    # Build SMTP username
    prefix = user_id[:8]
    suffix = user_id[8:16]
    username = f"scanner@{prefix}.{suffix}.wescan.net"
    conn.execute('UPDATE user SET smtp_password = ? WHERE id = ?', (hashed, user_id))
    conn.commit()
    print(f"SMTP Username: {username}")
    print(f"SMTP Password: {password}")
    print("--- Save this password. It won't be shown again. ---")
    conn.close()


def list_recipients(user_id):
    conn = get_db()
    rows = conn.execute(
        'SELECT id, email, display_name, is_active FROM recipient WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    print(f"{'ID':<8} {'Email':<35} {'Name':<20} {'Active'}")
    print("-" * 70)
    for r in rows:
        print(f"{r['id'][:8]:<8} {r['email']:<35} {r['display_name'] or '-':<20} {r['is_active']}")
    conn.close()


def stats():
    conn = get_db()
    total_users = conn.execute('SELECT COUNT(*) FROM user').fetchone()[0]
    free = conn.execute("SELECT COUNT(*) FROM user WHERE plan='free'").fetchone()[0]
    enterprise = conn.execute("SELECT COUNT(*) FROM user WHERE plan='enterprise'").fetchone()[0]
    today = conn.execute("SELECT COUNT(*) FROM usage_stat WHERE date(sent_at) = date('now')").fetchone()[0]
    all_time = conn.execute('SELECT COUNT(*) FROM usage_stat').fetchone()[0]
    print(f"Users: {total_users} (Free: {free}, Enterprise: {enterprise})")
    print(f"Emails: {all_time} total, {today} today")
    conn.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scanner2Email Admin CLI')
    parser.add_argument('action', choices=['users', 'set-plan', 'set-admin', 'smtp', 'recipients', 'stats'])
    parser.add_argument('--user', help='User ID')
    parser.add_argument('--plan', help='Plan name (free/enterprise)')

    args = parser.parse_args()

    if args.action == 'users':
        list_users()
    elif args.action == 'set-plan':
        if not args.user or not args.plan:
            print("Usage: manage-users.py set-plan --user USER_ID --plan free|enterprise")
            sys.exit(1)
        set_plan(args.user, args.plan)
    elif args.action == 'set-admin':
        if not args.user:
            print("Usage: manage-users.py set-admin --user USER_ID")
            sys.exit(1)
        set_admin(args.user)
    elif args.action == 'smtp':
        if not args.user:
            print("Usage: manage-users.py smtp --user USER_ID")
            sys.exit(1)
        generate_smtp(args.user)
    elif args.action == 'recipients':
        if not args.user:
            print("Usage: manage-users.py recipients --user USER_ID")
            sys.exit(1)
        list_recipients(args.user)
    elif args.action == 'stats':
        stats()
