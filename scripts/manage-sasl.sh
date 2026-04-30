#!/bin/bash
set -e

ACTION=$1
USERNAME=$2
PASSWORD=$3

case $ACTION in
    "add")
        echo $PASSWORD | saslpasswd2 -p -c -u wescan.net $USERNAME
        ;;
    "delete")
        saslpasswd2 -d -u wescan.net $USERNAME
        ;;
    *)
        echo "Usage: $0 {add|delete} username [password]"
        exit 1
        ;;
esac

# Update permissions
chown postfix:postfix /etc/sasldb2
