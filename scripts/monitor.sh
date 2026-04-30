#!/bin/bash

check_service() {
    if ! systemctl is-active --quiet $1; then
        systemctl restart $1
        echo "Service $1 restarted" | mail -s "WeScan Alert" admin@wescan.net
    fi
}

check_disk() {
    USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ $USAGE -gt 80 ]; then
        echo "Disk usage at ${USAGE}%" | mail -s "WeScan Alert" admin@wescan.net
    fi
}

# Check services
check_service postfix
check_service nginx
check_service wescan

# Check disk space
check_disk
