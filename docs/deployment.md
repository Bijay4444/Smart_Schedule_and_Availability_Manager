# Deployment preparation

## Step 1: settings separation

The existing layout follows [HackSoft's settings pattern](https://github.com/HackSoftware/Django-Styleguide#settings).
The initial local/production files were identical imports; they now have distinct
defaults and startup requirements. No application dependencies or migrations
were added, and scheduling behavior is unchanged.

```text
config/
  env.py                 shared django-environ reader
  django/
    base.py              shared applications, middleware, database, templates
    local.py             development .env loading and local defaults
    production.py        deployment checks and secure defaults
    test.py              disposable-database test profile
  settings/              future optional integration modules
```

Python executes the selected profile from top to bottom. Local/test read `.env`
before importing `base.py`, so the shared settings receive those values. Existing
process variables win over file values. Production imports the base without
reading a file, then applies its defaults and checks. This is a deliberate
adaptation of the style guide's dotenv example to isolate deployment configuration.
Optional integrations should still be defined/imported in the shared base and
enabled through environment flags.

`manage.py` selects local settings unless `--settings` or a process-level
`DJANGO_SETTINGS_MODULE` selects another profile. WSGI/ASGI default to production.
The `.env` file cannot select the profile: Django needs to choose its settings
module before it can execute that file-loading code.

### Local and test behavior

Local defaults to `DEBUG=True`, loopback hostnames, and HTTP-friendly cookies.
The existing root `.env` and local PostgreSQL Unix-socket setup continue to work.
Explicit environment values can override development defaults.

Tests load database values from the environment or root `.env` and retain
Django's separate `test_<database>` lifecycle. They provide a test-only secret
fallback before reading `.env`, use the fast test password hasher, and disable
HTTPS redirects, secure cookies, HSTS, and forwarded-protocol trust for test
clients. There is no switch to SQLite; PostgreSQL constraints remain tested.

### Production environment

Use [.env.production.example](../.env.production.example) as a variable reference.
Django does not load this file automatically. Set its real values in the hosting
service or explicitly inject them into a process/container when that is configured.
Keep real credentials out of Git. The local `.env` was not edited.

| Variable | Production behavior |
| --- | --- |
| `DJANGO_SETTINGS_MODULE` | `config.django.production` for deployment commands/processes. |
| `DJANGO_SECRET_KEY` | Required; at least 50 characters, at least 5 distinct characters, no `django-insecure-` prefix. Generate a separate random deployment secret. These checks follow Django's basic deployment-check criteria, not a guarantee of randomness. |
| `DJANGO_DEBUG` | Must be false; enabling it stops production startup. |
| `DJANGO_ALLOWED_HOSTS` | Required comma-separated hostnames without schemes or paths; bare `*` rejected. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated origins including `https://`; configure any deployment origins that need this trust. Same-origin CSRF validation still applies normally. |
| `DATABASE_URL` | Optional PostgreSQL URL; takes precedence over `PG*` connection fields when nonempty. URL-encode reserved characters in credentials. |
| `PGDATABASE`, `PGUSER`, `PGHOST`, `PGPASSWORD` | All required when a URL is absent. No production fallback to OS usernames, local socket, or default database. URLs must also specify database, user, host, and password. |
| `PGPORT` | Defaults to 5432 when using separate fields. |
| `PGSSLMODE` | Overrides a URL's `sslmode`; defaults to `require` in production if absent from both. |
| `PGSSLROOTCERT` | Optional CA certificate path, preserving other URL query options. |

For example, a URL can contain `?sslmode=verify-full&connect_timeout=10`.
`sslmode=require` requests encrypted transport; it is not a claim that hostname
verification is configured. The Azure database/TLS certificate choice will be
verified when selecting the hosting services.

### HTTPS and proxy defaults

Production defaults enable HTTPS redirects, secure session/CSRF cookies, and
one-hour HSTS. These defaults can be changed through the corresponding
`DJANGO_SECURE_SSL_REDIRECT`, `DJANGO_SESSION_COOKIE_SECURE`,
`DJANGO_CSRF_COOKIE_SECURE`, and `DJANGO_SECURE_HSTS_SECONDS` variables.
Run deployment checks against the actual environment after any override.

HSTS include-subdomains and preload default to false and are exposed through
`DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` and `DJANGO_SECURE_HSTS_PRELOAD`. Do not
enable these merely to silence warnings: first verify HTTPS coverage for the
selected domain and its subdomains. The one-hour setting allows an initial
HTTPS rollout before choosing a longer duration.

Forwarded-protocol trust defaults to off. If the final hosting proxy strips
client-supplied `X-Forwarded-Proto` and sets a trustworthy value, enable
`DJANGO_TRUST_X_FORWARDED_PROTO`. Django will then use
`("HTTP_X_FORWARDED_PROTO", "https")` to recognize HTTPS behind that proxy.
This must match the actual proxy to avoid redirect loops and false secure-request
claims. See [Django's proxy setting](https://docs.djangoproject.com/en/6.1/ref/settings/#secure-proxy-ssl-header).

### Commands and verification

```bash
uv run python manage.py check
uv run pytest tests/test_config.py

# With deployment variables already supplied to the process:
uv run python manage.py check --deploy --settings=config.django.production
```

Configuration tests run in fresh subprocesses with a temporary project `.env`,
so they verify isolation without reading or printing the developer's secrets.
Coverage includes environment precedence, production dotenv exclusion,
debug/host/secret/credential rejection, PostgreSQL-only URLs, encoded passwords,
TLS options, explicit proxy trust, security defaults, and test-profile isolation.

Verified on 22 November 2026: all 31 configuration tests and the full 505-test
PostgreSQL suite pass. The development system check reports no issues. A
production `check --deploy` with example process variables reports only
`security.W005` (HSTS subdomains) and `security.W021` (HSTS preload), intentionally
left disabled until the deployed domain is verified. That check does not connect
to an Azure database or prove the example credentials work.

The [Django deployment checklist](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/)
is the baseline for deployment verification. Passing settings startup does not
verify network access, database credentials, HTTPS, or static-file delivery.

## Step 2: Docker

### Image and runtime

`Dockerfile` uses Python 3.13.15 on Debian Bookworm and a separate build stage
with uv 0.12.13. `uv sync --locked --no-dev --no-install-project` installs the
runtime dependencies from `uv.lock`; the runtime image excludes uv and pytest.
Base image version tags are pinned, but tags and OS updates can change over
time; this is not a claim of bit-for-bit image reproducibility. The PostgreSQL
image tracks the supported 17.x Bookworm line; do not change its major version
against an existing volume without a database upgrade plan.

Two runtime dependencies were added:

- [Gunicorn](https://gunicorn.org/guides/docker/) is the production WSGI server.
  `config/gunicorn.py` defaults to two workers with two threads each, logs to
  stdout/stderr, and supports `PORT`, `WEB_CONCURRENCY`, `GUNICORN_THREADS`, and
  `GUNICORN_TIMEOUT`. Access logs omit query strings, cookies, and authorization
  headers. Proxy-header trust is not enabled automatically.
- [WhiteNoise](https://whitenoise.readthedocs.io/en/stable/django.html) serves
  CSS, JavaScript, and fonts without adding another web-server container.
  The shared base defines compressed manifest storage; local/test profiles
  retain immediate source-file access without requiring `collectstatic`.

Static files are collected during the build using shared base settings with a
public, build-only placeholder key. No real runtime secret, database password,
or live database connection is needed to collect assets. Deployment credentials
are injected only when the image runs. Gzip variants and content hashes support
compressed delivery and immutable caching. Bootstrap continues to use its
existing pinned CDN stylesheet; this task does not change frontend styling.

The final process runs as UID/GID 10001. The build context uses an allowlist in
`.dockerignore`, excluding `.env` files, host `.venv`, Git history, screenshots,
documents, presentation files, tests, and local tools. Only application code,
assets, locked dependencies, and the health-probe script enter the image.
System timezone data supports the existing Halifax scheduling rules.

### Local Compose preview

`compose.yaml` runs three services:

1. `db`: PostgreSQL on a private Compose network with a persistent named volume.
   Its health check uses TCP, avoiding the temporary socket-only server used
   during first initialization. No database port is published to the host.
2. `migrate`: one application container runs `manage.py migrate --noinput` after
   PostgreSQL is healthy. It exits on success or failure. The ordinary local
   PostgreSQL image supports the existing `btree_gist` migration.
3. `web`: starts Gunicorn only after migrations complete successfully. Health
   checks monitor `/healthz/`. Containers use read-only application files, a
   temporary `/tmp`, dropped capabilities, and no-new-privileges.

This dependency order follows [Docker Compose readiness conditions](https://docs.docker.com/compose/how-tos/startup-order/).
Web workers do not run migrations themselves. Azure deployment will need the
equivalent single migration job before rolling out web replicas.

```bash
# Creates .env.docker only if absent, with newly generated local secrets.
uv run python scripts/setup_docker_env.py

docker compose --env-file .env.docker config --quiet
docker compose --env-file .env.docker up --build -d --wait
docker compose --env-file .env.docker exec web python manage.py seed_demo
```

Open <http://localhost:8080/>. Seeding is optional and affects only this new
container database. Use the documented fictional accounts or create an account
with `docker compose --env-file .env.docker exec web python manage.py createsuperuser`.
No accounts are built into the image or created automatically at startup.
The seed command's report currently prints native port-8000 URLs; use port 8080
for those paths when running this Compose preview.

The setup helper does not print secrets, writes `.env.docker` with mode 0600,
and never overwrites existing values. The original `.env` is not read or edited.
Always pass `--env-file .env.docker`; this prevents Compose from accidentally
using the native development `.env` as its interpolation file. Exported shell
variables take precedence over Compose env-file values.

Only `127.0.0.1:8080` is published. Change `APP_PORT` in `.env.docker` if needed.
The local preview runs the production profile with explicit **local HTTP**
overrides: HTTPS redirect, secure cookies, HSTS, and database TLS are disabled.
These overrides exist in Compose, not in the image's production defaults.
Use `.env.production.example` for Azure; do not copy the local Compose overrides
into a public deployment.

### Updates and persistence

```bash
# Rebuild after application, dependency, or static-file changes.
docker compose --env-file .env.docker up --build -d --wait

docker compose --env-file .env.docker ps --all
docker compose --env-file .env.docker logs --tail=50 web migrate
docker compose --env-file .env.docker exec web python manage.py check

# Stop and later resume without deleting the database volume.
docker compose --env-file .env.docker stop
docker compose --env-file .env.docker up -d --wait
```

The named volume is separate from the native application's database and survives
container restarts/recreation. Keep `.env.docker` with it: changing
`POSTGRES_PASSWORD` does not update an already-initialized database user's password.
Do not remove the database volume when simply stopping or updating the app.
This persistent volume is local storage, not a backup policy.

### Health and verification

`/healthz/` answers GET/HEAD with plain `ok` and `Cache-Control: no-store`.
It reads no database or user data, needs no login, and rejects writes. Only this
stateless endpoint is exempt from HTTPS redirects so internal HTTP liveness
probes work when production HTTPS redirects are enabled. It means the process
can answer requests, not that the database or migrations are ready; Compose
uses separate database and migration readiness checks.
The probe connects to loopback while sending a hostname from
`DJANGO_ALLOWED_HOSTS`, so public-domain-only host validation stays intact.

`tests/test_deployment.py` verifies liveness without database access, method
restrictions, the narrow HTTPS exception, and real collected/hashed/gzipped CSS
served through WhiteNoise without `runserver`. `tests/test_docker_setup.py`
checks secret-file permissions, native-environment preservation, and safe reruns.

Verified runtime behavior:

- The final full PostgreSQL regression suite passes all **513 tests**.
- The image builds successfully; PostgreSQL and web report healthy, and the
  migration job exits successfully. Django system checks pass in the container.
- Login, the weekly board, availability, and a CSRF-protected shift-check POST
  pass HTTP smoke checks through Gunicorn.
- All four page asset URLs tested are served; CSS is gzipped and hashed static
  assets have immutable cache headers. The image contains the static manifest.
- Runtime UID is 10001. The image does not contain `.env`, `.env.docker`, Git
  history, tests, presentation files, or pytest.
- Stopping/restarting the database and web services preserves the demo account
  data; the same login/scheduling/asset smoke checks pass after restart.
- A temporary container with only a public hostname allowed and HTTPS redirects
  enabled passes its internal health probe, while normal login requests still
  redirect to HTTPS.

## Step 3: Azure

The [single-VM deployment guide](azure_vm_deployment.md) defines the demo setup:
Django, PostgreSQL and HTTPS together on one Azure VM. It is now deployed with
verified HTTPS, authenticated workflows and an off-VM database backup. See
[live deployment status](azure_vm_status.md).
The [managed-services alternative](azure_deployment.md) remains documented.
The running single-VM setup was explicitly approved. Public hosting extends
the original local demonstration scope.
