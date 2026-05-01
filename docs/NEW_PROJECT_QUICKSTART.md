# New Project Quick-Start

_Pattern extracted from WeScan development. Use as a template to deploy similar projects fast._

## 1. Pre-Requisites (get before you start)

| Item | Purpose |
|------|---------|
| Domain name + DNS access | Point A/NS to VPS IP |
| Cloudflare account | Turnstile site key + secret key |
| Google OAuth credentials | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Microsoft OAuth credentials | `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET` |
| Stripe account | Publishable key, secret key, webhook secret, price IDs |
| VPS (e.g. DO $12/mo droplet) | Ubuntu 22.04+, 2GB RAM, public IP |
| SMTP / Postfix domain | Configure MX/SPF/DKIM if sending mail |

**One-time setup on dev machine:**
- Homebrew: `python3`, `git`, `rsync`
- `.env` file with all secrets (template below)

## 2. Day-1 Server Setup (copy-paste)

```bash
# Connection
ssh root@<vps-ip>

# Essentials
apt update && apt upgrade -y
apt install -y nginx certbot python3 python3-venv postfix ufw git

# Firewall
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 587/tcp
ufw enable

# App directory
mkdir -p /opt/<project>
useradd -r -s /bin/false www-data  # might already exist
```

## 3. App Structure

```
/opt/<project>/
├── venv/               # python3 -m venv venv
├── app/                # Flask app
│   ├── __init__.py
│   ├── config.py
│   ├── routes/
│   │   ├── auth.py     # OAuth + email OTP + Turnstile verify
│   │   ├── admin.py    # admin_required decorator
│   │   ├── dashboard.py
│   │   └── payments.py # Stripe
│   ├── templates/
│   │   ├── admin/
│   │   ├── dashboard/
│   │   └── base.html
│   └── static/
├── docs/               # Marketing site (static HTML)
│   ├── index.html
│   ├── signup.html
│   ├── verify.html
│   └── ...
├── run.py
├── requirements.txt
└── .env                # NOT in git
```

## 4. Required .env Template

```bash
SECRET_KEY=<random-64-char-string>
DATABASE_URL=sqlite:////opt/<project>/app.db  # or PostgreSQL
TURNSTILE_SECRET_KEY=<from Cloudflare>
GOOGLE_CLIENT_ID=<from GCP>
GOOGLE_CLIENT_SECRET=<from GCP>
MICROSOFT_CLIENT_ID=<from Entra/Azure>
MICROSOFT_CLIENT_SECRET=<from Entra/Azure>
STRIPE_PUBLIC_KEY=<pk_live_...>
STRIPE_SECRET_KEY=<sk_live_...>
STRIPE_WEBHOOK_SECRET=<whsec_...>
STRIPE_PRICE_AUD=<price_id>
STRIPE_PRICE_USD=<price_id>
```

## 5. Deploy Workflow (fast path)

```bash
# 1. Static files only
rsync -avz docs/ root@<vps>:/opt/<project>/docs/

# 2. Or whole app (excluding .env/venv/.git/__pycache__)
rsync -avz --exclude='.env' --exclude='venv' --exclude='__pycache__' --exclude='.git' ./ root@<vps>:/opt/<project>/

# 3. Fix permissions (ALWAYS — rsync preserves Mac ownership)
ssh root@<vps> "chown -R www-data:www-data /opt/<project>/app/templates && chmod -R 640 /opt/<project>/app/templates && chown www-data:www-data /opt/<project>/docs/*.html && chmod 644 /opt/<project>/docs/*.html"

# 4. Restart if templates or Python files changed
ssh root@<vps> "systemctl restart <project>"
```

**Critical gotchas (solved):**
- Rsync preserves `501:staff` → gunicorn runs as `www-data` → `chown` always
- Gunicorn caches Jinja templates in memory → `systemctl restart` always
- Template directory needs `a+x` (traverse) permission

## 6. Systemd Service Template

`/etc/systemd/system/<project>.service`:

```ini
[Unit]
Description=<Project Name>
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/<project>
Environment="PATH=/opt/<project>/venv/bin"
ExecStart=/opt/<project>/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 --error-logfile /var/log/<project>/error.log --access-logfile /var/log/<project>/access.log --capture-output run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Create log directory: `mkdir -p /var/log/<project> && chown www-data:www-data /var/log/<project>`

## 7. Nginx Config Template

`/etc/nginx/sites-enabled/<domain>`:

```nginx
server {
    listen 80;
    server_name <domain> www.<domain>;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name <domain> www.<domain>;

    ssl_certificate /etc/letsencrypt/live/<domain>/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<domain>/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    root /opt/<project>/docs;
    index index.html;

    # Static files
    location / {
        try_files $uri $uri/ =404;
    }

    # Flask routes
    location ~ ^/(dashboard|auth|admin|login|logout|api|static|checkout|webhook|portal) {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    client_max_body_size 26M;

    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header Strict-Transport-Security "max-age=31536000";
}
```

## 8. Cloudflare Turnstile (frontend gotcha)

**Setup:**
- Site key → frontend `<div class="cf-turnstile" data-sitekey="..."/>`
- Secret key → `TURNSTILE_SECRET_KEY` in `.env`

**Form auto-submit — Must wait for token:**

```js
// BAD (will empty-submit → captcha_failed)
if (digits === 6) form.submit();

// GOOD
if (digits === 6) {
  const token = form.querySelector('[name="cf-turnstile-response"]');
  if (token && token.value) {
    form.submit();
  } else {
    // Poll until Turnstile resolves
    const interval = setInterval(() => {
      const t = form.querySelector('[name="cf-turnstile-response"]');
      if (t && t.value) { clearInterval(interval); form.submit(); }
    }, 200);
  }
}
```

## 9. Sub-Agent Workflow (delegation model)

Sub-agents come from a **separate system** with no back-and-forth. Specs must be one-shot, self-contained, and anticipate everything.

### Flow
```
You (PM/Architect)                  Sub-Agent (Coder)
  │                                     │
  ├─ Write comprehensive spec ────────► │ (offline, no questions)
  │                                     ├─ Reads listed files
  │                                     ├─ Matches existing patterns
  │                                     ├─ Handles edge cases
  │                                     ├─ Checks no regressions
  │◄─ Result + full diff ───────────── │
  │                                     │
  ├─ Review (takes <2 min)
  ├─ Make minor tweaks (takes <1 min)
  └─ Deploy
```

### Spec Template (comprehensive, one-shot)
```
## Task
One-line description

## Files
- /abs/path/to/file.ext — what this file does, why it needs changing. Read this first.

## Context
- Framework: Flask + Jinja templates + Tailwind CSS CDN (no build step)
- Styling: Inter font, inline styles, Tailwind utility classes, rounded corners, gray borders, sparse palette
- Layout: single-page designs with sections, stats in grid rows, tables with expandable rows
- Auth: Flask-Login, OAuth + email OTP, admin_required decorator
- The project follows existing patterns — match them exactly

## What to Do (in order)
1. Read target file(s) to understand current structure
2. Make changes:
   - At [location], change [X] to [Y]
   - Add [new block] after [existing block]
   - Update [JS function] to handle [new case]
3. Verify: check all template variables still match the route handler, check all CSS classes still exist

## What NOT to Do
- Don't modify files outside the listed ones
- Don't add new dependencies
- Don't change visual style beyond the request
- Don't refactor existing code

## Edge Cases
- Empty state: what shows when there's no data?
- Error state: what shows when API fails?
- Mobile: does it work at 375px? (use Tailwind responsive breakpoints)
- Auth: does unauthenticated user get redirected properly?

## Acceptance Criteria
- [ ] Page X loads without errors
- [ ] When user does Y, result is Z
- [ ] No regressions in feature W
- [ ] Template renders all dynamic variables
- [ ] Works at mobile width
```

### Review Checklist (takes <2 min)
- [ ] Matches existing patterns (inline styles? Jinja scope?)
- [ ] No broken template variables (check against route handler)
- [ ] Edge cases handled (empty, error, mobile)
- [ ] No new dependencies
- [ ] Passes basic manual test

## 10. UI Patterns (proven)

**Stats grid:** Two separate rows (not 1 complex grid with spanning)
```html
<!-- Row 1: 4–6 big cards -->
<div class="grid grid-cols-4 gap-3">...</div>
<!-- Row 2: compact pills -->
<div class="flex flex-wrap gap-2">...</div>
```

**Collapsible sections:** Full-width button + `display:none` body + chevron
```html
<button onclick="toggleSection()">
  Title <span id="chevron">▸</span>
</button>
<div id="body" style="display:none">...</div>
```

**Tailwind:** CDN approach (`<script src="https://cdn.tailwindcss.com">`) works for small projects. No build step needed.

## 10. Server Monitoring

```bash
# App logs
tail -f /var/log/<project>/error.log
tail -f /var/log/<project>/access.log

# Service health
systemctl status <project>
systemctl restart <project>

# Nginx
nginx -t && systemctl reload nginx

# SSL renewal (auto via certbot)
certbot renew --dry-run

# Disk / memory
df -h / && free -h
```

## 11. Day-1 Launch Checklist

- [ ] DNS A record points to VPS IP
- [ ] SSL certificate issued (`certbot --nginx`)
- [ ] `.env` has all secrets (no placeholder values)
- [ ] App boots: `curl -s http://127.0.0.1:5000/ | head`
- [ ] Nginx passes through: `curl -s https://<domain>/`
- [ ] OAuth redirect URIs registered (Google, Microsoft)
- [ ] Stripe webhook endpoint configured
- [ ] Postfix listening on port 587
- [ ] UFW allows 22, 80, 443, 587
- [ ] Log directories exist and writable by www-data
- [ ] Permissions checked: `chown -R www-data:www-data /opt/<project>`
