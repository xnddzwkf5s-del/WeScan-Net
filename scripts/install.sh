#!/bin/bash
set -e

# Accept parameters
DOMAIN="wescan.net"
CF_API_TOKEN=$1
CF_ZONE_ID=$2
GOOGLE_CLIENT_ID=$3
GOOGLE_CLIENT_SECRET=$4
STRIPE_SECRET_KEY=$5

# Install required packages
apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    postfix \
    postfix-sasl \
    sasl2-bin \
    nginx \
    ufw \
    fail2ban \
    certbot \
    python3-certbot-nginx \
    sqlite3

# Create application directory
mkdir -p /opt/wescan
cd /opt/wescan

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env file
cat > /opt/wescan/.env << EOL
DOMAIN=${DOMAIN}
CF_API_TOKEN=${CF_API_TOKEN}
CF_ZONE_ID=${CF_ZONE_ID}
GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}
EOL
chmod 600 /opt/wescan/.env

# Configure Postfix
cat > /etc/postfix/main.cf << EOL
smtpd_banner = \$myhostname ESMTP WeScan
biff = no
append_dot_mydomain = no
readme_directory = no

smtpd_tls_cert_file=/etc/letsencrypt/live/${DOMAIN}/fullchain.pem
smtpd_tls_key_file=/etc/letsencrypt/live/${DOMAIN}/privkey.pem
smtpd_use_tls=yes
smtpd_tls_auth_only = yes

smtpd_sasl_type = cyrus
smtpd_sasl_path = smtpd
smtpd_sasl_auth_enable = yes
smtpd_sasl_security_options = noanonymous

smtpd_recipient_restrictions =
    permit_sasl_authenticated,
    reject_unauth_destination

content_filter = wescan_filter:dummy
message_size_limit = 26214400

myhostname = smtp.${DOMAIN}
mydestination = \$myhostname, localhost
inet_interfaces = all
inet_protocols = ipv4
EOL

# Configure master.cf
cat >> /etc/postfix/master.cf << EOL
wescan_filter unix - n n - 10 pipe
    flags=Rq user=nobody argv=/opt/wescan/scripts/content-filter.py \${sender} \${recipient}
EOL

# Configure Nginx
cat > /etc/nginx/sites-available/${DOMAIN} << EOL
server {
    server_name ${DOMAIN};
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
    client_max_body_size 26M;
    client_body_buffer_size 128k;
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-XSS-Protection "1; mode=block";
    add_header X-Content-Type-Options "nosniff";
    add_header Strict-Transport-Security "max-age=31536000";
    # Rate limiting
    limit_req_zone \$binary_remote_addr zone=one:10m rate=10r/s;
    limit_req zone=one burst=5;
}
EOL

ln -s /etc/nginx/sites-available/${DOMAIN} /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Configure UFW
ufw allow ssh
ufw allow http
ufw allow https
ufw allow 587/tcp
ufw --force enable

# Get SSL certificate
certbot --nginx -d ${DOMAIN} -d smtp.${DOMAIN} --non-interactive --agree-tos -m admin@${DOMAIN}

# Setup systemd service
cat > /etc/systemd/system/wescan.service << EOL
[Unit]
Description=WeScan Email Relay
After=network.target

[Service]
User=www-data
WorkingDirectory=/opt/wescan
Environment="PATH=/opt/wescan/venv/bin"
ExecStart=/opt/wescan/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 run:app
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Configure sudoers
cat > /etc/sudoers.d/wescan << EOL
www-data ALL=(ALL) NOPASSWD: /opt/wescan/scripts/manage-sasl.sh
EOL
chmod 440 /etc/sudoers.d/wescan

# Initialize database
cd /opt/wescan && . venv/bin/activate && python3 -c "
from app import create_app, db
from app.models import User, Recipient, UsageStat, Plan
app = create_app()
with app.app_context():
    db.create_all()
    print('Database initialized')
"

# Start services
systemctl enable wescan
systemctl start wescan
systemctl restart nginx postfix

echo "Installation complete!"
