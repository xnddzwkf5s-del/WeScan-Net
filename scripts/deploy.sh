#!/usr/bin/env bash
set -euo pipefail

SERVER="root@170.64.232.39"
REMOTE_DIR="/opt/wescan"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  echo "Usage: $0 [deploy|rollback] [backup-file]"
  echo ""
  echo "Commands:"
  echo "  deploy              Rsync local code → server, fix perms, restart"
  echo "  rollback [file]     Restore from a backup tarball (default: latest)"
  exit 1
}

if [ $# -lt 1 ]; then usage; fi

case "$1" in
  deploy)
    echo "=== Backing up remote current release..."
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    ssh "$SERVER" "cd $REMOTE_DIR && tar czf /tmp/wescan-pre-deploy-${TIMESTAMP}.tar.gz ."

    echo "=== Syncing documentation..."
    rsync -avz "$LOCAL_DIR/docs/" "$SERVER:$REMOTE_DIR/docs/"

    echo "=== Syncing application code..."
    rsync -avz \
      --exclude='.env' \
      --exclude='venv' \
      --exclude='__pycache__' \
      --exclude='.git' \
      --exclude='*.pyc' \
      --exclude='.DS_Store' \
      "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

    echo "=== Fixing ownership (CRITICAL - rsync preserves 501:staff)..."
    ssh "$SERVER" "chown -R www-data:www-data $REMOTE_DIR && chmod 755 $REMOTE_DIR && find $REMOTE_DIR/app/templates -type d -exec chmod 755 {} + && find $REMOTE_DIR/app/templates -type f -exec chmod 640 {} + && chmod 755 $REMOTE_DIR/docs/*.html 2>/dev/null; true"

    echo "=== Restarting wescan service..."
    ssh "$SERVER" "systemctl restart wescan"

    echo "=== Done. Verify: systemctl status wescan"
    ;;

  rollback)
    echo "=== Available backups:"
    ssh "$SERVER" "ls -1t /tmp/wescan-pre-deploy-*.tar.gz 2>/dev/null" || {
      echo "No backups found at /tmp/wescan-pre-deploy-*.tar.gz"
      exit 1
    }

    if [ -n "${2:-}" ]; then
      BACKUP="$2"
    else
      BACKUP=$(ssh "$SERVER" "ls -1t /tmp/wescan-pre-deploy-*.tar.gz 2>/dev/null | head -1")
      if [ -z "$BACKUP" ]; then
        echo "No backup found."
        exit 1
      fi
      echo "=== Using latest backup: $BACKUP"
    fi

    echo "=== Restoring from $BACKUP..."
    ssh "$SERVER" "cd $REMOTE_DIR && rm -rf ./* && tar xzf \"$BACKUP\" && chown -R www-data:www-data $REMOTE_DIR && find $REMOTE_DIR/app/templates -type d -exec chmod 755 {} + && find $REMOTE_DIR/app/templates -type f -exec chmod 640 {} + && chmod 755 $REMOTE_DIR/docs/*.html 2>/dev/null; true && systemctl restart wescan"
    echo "=== Rollback complete."
    ;;

  *)
    usage
    ;;
esac
