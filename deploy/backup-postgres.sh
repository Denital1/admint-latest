#!/bin/sh
set -eu
umask 077
backup_once() {
    backup_file="/backups/admint-$(date -u +%Y%m%dT%H%M%SZ).dump"
    if pg_dump --format=custom --no-owner --no-acl --file="$backup_file.partial" && pg_restore --list "$backup_file.partial" >/dev/null; then
        mv "$backup_file.partial" "$backup_file"
        echo "Database backup completed."
    else
        rm -f "$backup_file.partial"
        echo "Database backup failed." >&2
        return 1
    fi
}
if [ "${1:-}" = "--once" ]; then
    backup_once
else
    while :; do
        backup_once || true
        sleep 86400
    done
fi
