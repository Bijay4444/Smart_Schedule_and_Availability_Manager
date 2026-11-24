#!/bin/sh
# Writes a consistent custom-format PostgreSQL dump; copy it off the VM.
set -eu
umask 077
cd "$(dirname "$0")"
unset APP_HOST APP_HOST_ALIAS APP_IMAGE DJANGO_SECRET_KEY POSTGRES_PASSWORD
directory=${1:-backups}
mkdir -p "$directory"
temporary=$(mktemp "$directory/.backup.XXXXXX")
trap 'rm -f "$temporary"' EXIT
docker compose --env-file .env -f compose.yaml exec -T db \
    sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$temporary"
test -s "$temporary"
target="$directory/smart-schedule-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
mv "$temporary" "$target"
echo "Backup saved to $target. Copy it to private off-VM storage."
