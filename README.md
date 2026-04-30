# WeScan

Cloud-based scanner-to-email SMTP relay. Run your own. $6/mo on DigitalOcean.

## Architecture

```
Printer/Scanner ──TLS 587──▶ Postfix SASL (sasldb2)
                                  │
                                  ▼
                            Content Filter
                            (validates file type,
                             size, recipient whitelist)
                                  │
                                  ▼
                            Flask API ──▶ SQLite
                            Dashboard    (users, recipients,
                            OAuth Auth   usage stats)
                            Stripe
                                  │
                                  ▼
                            Outbound SMTP
```

Single DigitalOcean droplet. Everything on one box. Cloudflare for TLS + DNS.

## Project Structure

```
wescan/
├── .github/workflows/deploy.yml   # CI/CD pipeline
├── app/
│   ├── __init__.py                # Flask factory + DB init
│   ├── config.py                  # Env config
│   ├── models.py                  # User, Recipient, UsageStat, Plan
│   ├── auth.py                    # OAuth (Google/MS/Apple) + SMTP password
│   ├── dashboard.py               # User dashboard
│   ├── api.py                     # Content filter validation API
│   ├── payments.py                # Stripe subscriptions
│   ├── admin.py                   # Admin panel
│   └── templates/index.html       # Landing page
├── config/
│   ├── nginx.conf                 # Performance + security tuning
│   ├── postfix-main.cf            # Reference Postfix config
│   └── wescan.service      # systemd unit
├── scripts/
│   ├── install.sh                 # One-command DO deploy
│   ├── manage-sasl.sh             # Postfix SASL user management
│   ├── content-filter.py          # Postfix pipe filter
│   ├── security.sh                # SSH + fail2ban + auto-updates
│   ├── backup.sh                  # Daily backup + rotation
│   ├── monitor.sh                 # Service health checks
│   └── manage-users.py            # CLI user management
├── migrate.py                     # Flask-Migrate entry point
├── requirements.txt
├── run.py
└── .env.example
```

## Deploy

One command:

```bash
sudo ./scripts/install.sh CF_API_TOKEN CF_ZONE_ID admin@email.com
```

Then fill in OAuth + Stripe keys in `/opt/wescan/.env`.

## Plans

| Feature | Free | Enterprise |
|---------|------|------------|
| Price | $0 | $20/mo or $200/yr |
| Recipients | 15 | 100 |
| File size | 10MB | 25MB |
| File types | PDF/JPG/PNG | PDF/JPG/PNG |
| Rate limit | 50/hr | 200/hr |
