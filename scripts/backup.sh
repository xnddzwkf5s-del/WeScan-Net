#!/bin/bash
# scanner2email - Daily backup
set -euo pipefail

INSTALL_DIR="/opt/scanner2email"
BACKUP_DIR="$INSTALL_DIR/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup database
cp "$INSTALL_DIR/data/scanner2email.db" "$BACKUP_DIR/db_$DATE.sqlite"

# Backup config
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" \
    "$INSTALL_DIR/.env" \
    "$INSTALL_DIR/config/" \
    /etc/postfix/main.cf \
    /etc/postfix/master.cf \
    /etc/nginx/sites-available/"$DOMAIN" 2>/dev/null || true

# Prune backups older than 14 days
find "$BACKUP_DIR" -name "db_*.sqlite" -mtime +14 -delete
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +14 -delete

echo "Backup complete: $DATE"
