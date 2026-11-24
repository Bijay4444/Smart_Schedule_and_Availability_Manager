#!/bin/sh
# Run from the private release bundle on the VM. Requires Docker access (sudo).
set -eu
cd "$(dirname "$0")"
test -f .env || { echo 'Missing private .env; run prepare_vm_deploy.py first.' >&2; exit 1; }
chmod 600 .env
# The private bundle is authoritative even when the caller has loaded a
# development environment. Compose normally prefers exported shell values.
unset APP_HOST APP_HOST_ALIAS APP_IMAGE DJANGO_SECRET_KEY POSTGRES_PASSWORD
if ! mkdir .deploy-lock 2>/dev/null; then
    echo 'A deployment may already be running. Inspect it before removing .deploy-lock.' >&2
    exit 1
fi
trap 'rmdir .deploy-lock' EXIT
compose() { docker compose --env-file .env -f compose.yaml "$@"; }
compose --profile ops config --quiet
# Pull dependencies before the maintenance window; the app image is loaded
# from an archive and cannot be silently replaced by a registry pull.
compose pull db proxy
compose stop proxy web
compose up -d --wait db
compose run --rm --no-deps migrate
compose run --rm --no-deps migrate python manage.py check --deploy
compose up -d --wait --no-deps web
# Liveness alone does not prove the database schema is current.
compose exec -T web python manage.py migrate --check
compose up -d --wait --no-deps proxy
echo 'Containers ready. Verify public HTTPS, login, and scheduling before sharing the URL.'
