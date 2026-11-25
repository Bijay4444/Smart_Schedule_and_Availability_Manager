# Smart Schedule and Availability Manager

[![Test and deploy](https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/Bijay4444/Smart_Schedule_and_Availability_Manager/actions/workflows/ci-cd.yml)

A Django application for people balancing classes, multiple jobs, and personal
commitments. It currently includes login/logout, private commitment sources,
one-time commitment management, a recurring scheduling engine, and a visual
weekly calendar with an agenda layout on phones, working-window configuration,
and shareable weekly availability. A proposed-shift screen checks unsaved offers
against working windows and commitments.

**Live Azure demo:** [Open Smart Schedule](https://schedule.khadkabijay.com.np/).
Guest login: **`schedule_demo` / `DemoSchedule!2026`**. This shared, non-admin
account contains fictional scheduling data; visitors can see each other's demo
edits. Keep personal information in your separate account. See the
[deployment status](docs/azure_vm_status.md).

## Current workflow

Pull requests run PostgreSQL tests and a Docker deployment rehearsal. Successful
pushes to `main` automatically deploy the tested image to Azure, with a database
backup and verified migrations. See the [CI/CD guide](docs/ci_cd.md).

Open <http://127.0.0.1:8000/week/> after signing in. Navigate weeks, select a day
to add a one-time commitment, or select a block for its full details. Overnight
commitments appear on both dates. The list remains available at
<http://127.0.0.1:8000/commitments/>:

1. Add a source such as Classes, Job A, or Personal and choose its color.
2. Add a one-time commitment with explicit start and end dates/times.
3. For overnight work, set the end to the following date.
4. If it overlaps another commitment, review the warning and explicitly confirm
   before saving. Overlaps remain marked on the list.
5. Edit a commitment or use its separate delete-confirmation page.

Times use Halifax time. One-time commitment forms reject ambiguous/nonexistent
daylight-saving clock times. See the
[development checklist](docs/development_checklist.md) for the remaining work.

Open `/availability/` or choose **Availability** to see available hours for a
Monday–Sunday week, then copy the employer-facing text. The output contains
dates and hours without private commitment details. Unresolved dates are marked
**Needs review** and incomplete weeks are copied as drafts. Manual text selection
works if clipboard access or JavaScript is unavailable. See the
[availability screen guide](docs/availability_screen.md) for behavior and tests.

Open `/check-shift/` or choose **Check a shift** to test an offer without saving
it. Results separate commitment conflicts from hours outside working windows;
unresolved dates require review. Overnight shifts and explicit repeated-hour
choices are supported. See the [shift-check guide](docs/proposed_shift_screen.md).

Open `/working-windows/` or choose **Working windows** in the navigation to set
weekly hours, multiple windows per weekday, and overnight windows. Future-effective
changes preserve earlier schedules. Full-date overrides can replace one date's
hours, close that date, or be removed to restore the weekly pattern. The dated
preview shows working windows before commitments are subtracted. See the
[working-window screen guide](docs/working_window_screens.md) for the workflow,
DST controls, architecture, and tests.

The recurring database foundation is now installed: stable series, dated
revisions, selected weekdays, and one-off exception storage. Backend services
now create/edit/end series, cancel/reschedule occurrences, and generate bounded
occurrences with automatic DST resolution and explicit review issues. Open
`/recurring/` to create a series, change future hours, end it, or inspect its
history. Calendar details offer one-off change/cancel actions. Recurring writes
require a current signed review; open-ended schedules show an explicit 12-month
warning preview. See the [recurring workflow guide](docs/recurring_workflow.md).
The existing
one-time save warning now checks recurring occurrences as well as one-time
commitments, and list badges retain those overlaps. Unresolved recurring clock
issues require acknowledgement and remain marked for review. Sources can be
archived through the service layer; archived commitments still block time and
remain editable.
Source-management buttons are not yet provided. See the
[database design](docs/database_design.md) for the approved schema and boundaries.
The [recurrence service guide](docs/recurrence_services.md) explains the backend
interfaces, time calculations, and tests.
The [availability service guide](docs/availability_services.md) explains dated
working windows, full-date overrides, availability subtraction, and proposed-shift
checks. These services support both one-time and recurring commitments, including
overnight boundaries and DST review issues. Migration 0004 adds their storage;
run migrations after starting the local PostgreSQL service.
The [calendar guide](docs/weekly_calendar.md) explains the frontend and its
desktop/mobile verification. Calendar overlap indicators include recurring
commitments. The [conflict service guide](docs/conflict_services.md) explains
save warnings, incomplete checks, long intervals, and simultaneous-write handling.

All existing application templates now share the same navigation, self-hosted
typography, forms, controls, and responsive patterns. The
[frontend style guide](docs/frontend_style.md) records the Impeccable installation
and how to extend the shared interface.

## What is installed

- Python 3.13 is selected by `.python-version` and managed by `uv`.
- Django provides the application, templates, admin, sessions, and authentication.
- Psycopg is the PostgreSQL driver. Its binary distribution avoids a local C
  compiler and PostgreSQL development-library requirement.
- django-environ reads typed environment values. Local/test profiles load the
  project-root `.env`; production reads deployment environment variables.
- Gunicorn serves Django's WSGI application in the container.
- WhiteNoise serves collected static assets with compression and versioned names.
- pytest and pytest-django provide the development test runner and Django test
  database integration.

Exact resolved versions are recorded in `uv.lock`. REST Framework will be added
when API work begins. Bootstrap CSS currently loads from a pinned CDN URL; no
Node.js build is needed. The Bootstrap styling requires an internet connection.

## Run with Docker

Docker Desktop must be running with WSL integration enabled for this distro.
From the project root:

```bash
uv run python scripts/setup_docker_env.py
docker compose --env-file .env.docker up --build -d --wait
docker compose --env-file .env.docker exec web python manage.py seed_demo
```

Open <http://localhost:8080/>. The existing fictional demo accounts/password from
the walkthrough below work after seeding this separate container database.
Alternatively, create your own account:

```bash
docker compose --env-file .env.docker exec web python manage.py createsuperuser
```

The setup helper creates private local secrets once and preserves them on rerun.
The native `.env` and native PostgreSQL database are not used by Compose.
`db` must be healthy and `migrate` must finish before `web` starts. The image runs
Gunicorn as a non-root user and serves static assets through WhiteNoise.

```bash
docker compose --env-file .env.docker ps --all
docker compose --env-file .env.docker logs --tail=50 web migrate
docker compose --env-file .env.docker stop
```

The local Compose preview binds only to `127.0.0.1`, uses HTTP, and deliberately
overrides HTTPS/cookie/database-TLS settings for that local environment. The
image's production defaults remain secure for the later Azure deployment.
PostgreSQL has no published port and persists data in a named Docker volume.
See [the Docker deployment guide](docs/deployment.md#step-2-docker) for architecture,
updates, persistence, health checks, and verification.

## Native local setup in WSL

Run commands from the project directory. Use the WSL terminal for both Django
and PostgreSQL.

### Python environment

```bash
uv sync --locked
```

There is no need to activate `.venv` when using `uv run`.

This checkout already has a generated, gitignored `.env`. For a fresh checkout,
copy `.env.example` to `.env`, generate a secret with the following command, and
replace `DJANGO_SECRET_KEY` in `.env` with the result:

```bash
cp .env.example .env
uv run python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Local and test settings automatically load the project-root `.env`. Environment
variables already set by your shell take precedence. Keep personal settings in
`.env`; `.env.example` is the shareable development template. Production ignores
this file; `.env.production.example` documents deployment variables.

### PostgreSQL

Django requires PostgreSQL 15 or newer. PostgreSQL was not installed in this WSL
distro when the project was initialized, and Docker Desktop's WSL integration
was not enabled. The native Ubuntu installation is the initial local path:

```bash
sudo apt update
sudo apt install postgresql
sudo service postgresql start
sudo -u postgres createuser --createdb "$USER"
sudo -u postgres createdb --owner="$USER" smart_schedule
```

Run the role/database creation commands once. If either already exists, keep the
existing object rather than deleting it. `--createdb` lets the development role
create the disposable database used by PostgreSQL integration tests.

Migrations also enable PostgreSQL's `btree_gist` extension, which prevents
overlapping effective revision periods for one series. It is included in the
current local PostgreSQL installation. On another server, ensure it is available
and the migration role can create it, or have its administrator enable it first.
See [Django's extension migrations](https://docs.djangoproject.com/en/6.1/ref/contrib/postgres/operations/#creating-extension-using-migrations).

The default Django configuration uses a local Unix socket (`PGHOST` is empty).
Ubuntu's default peer authentication matches the PostgreSQL role to your Linux
username, so this local connection needs no database password. Leave `PGUSER`
empty to use that username automatically. `PGDATABASE` defaults to
`smart_schedule`. The optional `PG*` fields in `.env.example` support another
database connection later.

Check the connection:

```bash
pg_isready
psql -d smart_schedule -c 'SELECT current_user, current_database();'
```

If the server is stopped after restarting WSL, run
`sudo service postgresql start` again.

### Create tables and sign in

After PostgreSQL is ready:

```bash
uv run python manage.py check
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Open <http://127.0.0.1:8000/> and sign in with the account you created. The admin
is at <http://127.0.0.1:8000/admin/>; additional demo accounts can be created
there. Logout uses a CSRF-protected POST form.

### Demo data for checking features

```bash
uv run python manage.py seed_demo
```

Sign in as `schedule_demo` with password `DemoSchedule!2026`. Also provided:
`schedule_demo_other` for privacy/full-day cases, `schedule_demo_empty` for
first-use screens, and `schedule_demo_dst` for clock changes and review states.
They use the same initial password and have no admin privileges. The command
prints dated links and expected results for calendar, recurrence/history,
conflicts, working windows/overrides, availability/copying, and shift checks.

Reruns preserve manual changes. `uv run python manage.py seed_demo --reset`
restores only the marked demo accounts and removes their experimental edits.
Use `--reset --week YYYY-MM-DD` to choose another demo week. Existing personal
accounts are preserved. Follow the complete [feature-testing walkthrough](docs/demo_data.md).

## Tests

The full suite uses PostgreSQL, including schema constraints, migration
preservation, archival/privacy rules, and concurrent revision insertion. Start
the local server and configure the development role before running:

```bash
uv run pytest
```

Django creates and removes a separate `test_smart_schedule` database for that
run. The application database remains separate. SQLite cannot run this schema's
PostgreSQL exclusion constraints. The test profile keeps PostgreSQL connection
settings from the environment or `.env` and uses a faster test-only password
hasher. Fresh databases receive all migrations, including `btree_gist`.

## Configuration

Configuration follows the [HackSoft settings pattern](https://github.com/HackSoftware/Django-Styleguide#settings)
described in [docs/config_pattern.md](docs/config_pattern.md):

```text
config/
├── django/
│   ├── base.py
│   ├── local.py
│   ├── production.py
│   └── test.py
├── settings/
│   └── __init__.py
├── env.py
├── urls.py
├── wsgi.py
└── asgi.py
```

`config/django/base.py` contains shared Django configuration and reads values
through the shared `env` object in `config/env.py`. It does not load `.env`.
`manage.py` defaults to `config.django.local`; WSGI and ASGI default to
`config.django.production`. The profiles have distinct behavior:

| Profile | Environment source | Behavior |
| --- | --- | --- |
| `local` | Process environment, then optional root `.env` | Debug on and localhost hosts by default; local PostgreSQL socket supported. |
| `production` | Process environment only | Debug must be off; explicit secret, hosts, and database credentials required; HTTPS/secure-cookie/TLS defaults. |
| `test` | Process environment, then optional root `.env` | Separate Django test database, test-only secret fallback, fast password hashing, HTTPS redirects disabled. |

Set `DJANGO_SETTINGS_MODULE` in the process environment
or use `manage.py --settings=...` to choose a different module. Set this variable
before Django starts; putting it only in `.env` is too late to select the module.

pytest defaults to `config.django.test`. Test overrides do not affect local or
production modules. The secret fallback is applied before reading `.env`, so a
local file's application secret does not replace the test-only default.

Future third-party settings belong in `config/settings/<integration>.py` and must
be imported at the end of `base.py`, so every environment sees them. Enable
optional integrations using an environment flag that defaults to false, and
require their credentials only when enabled. The package is currently empty
because no such integrations are configured.

Both environments accept the existing PostgreSQL `PG*` values or a PostgreSQL
`DATABASE_URL`. A nonempty URL takes precedence. `PGSSLMODE` and `PGSSLROOTCERT`
can supplement either connection format; production defaults to `sslmode=require`.

Production requires a strong secret of at least 50 characters, nonempty explicit
hosts (no `*`), and complete database credentials. Supply values using your hosting
service; `.env.production.example` is a reference, not an automatically loaded
file. Never reuse the local secret for deployment.

```bash
# Development (default)
uv run python manage.py runserver

# After setting the production variables in the process environment
uv run python manage.py check --deploy --settings=config.django.production
```

The [deployment guide](docs/deployment.md) explains profile inheritance,
HTTPS/proxy settings, and the Docker workflow. Settings separation, the production
container server, and static-file serving are implemented. The
[Azure hosting guide](docs/azure_deployment.md) includes infrastructure templates,
the cost proposal, and staged deployment with verified migrations before public
access. For the university demo, the revised recommendation is
[one Azure VM running Django and PostgreSQL](docs/azure_vm_deployment.md).
Preparing these files does not provision Azure resources.

## Structure and authentication choice

- `config/`: settings, routes, and server entry points.
- `accounts/`: an `AbstractUser` subclass and its admin registration/migration.
- `core/`: the authenticated home page.
- `scheduling/`: sources, one-time workflow, recurring storage models, and services.
- `templates/` and `static/`: the frontend.
- `tests/`: authentication, ownership, CRUD, constraints, time zones, overlaps, and CSRF behavior.

The browser uses Django's existing username/password login views, forms, and
session cookies. This satisfies the current demo without another auth package.
The custom user model inherits the standard behavior and is configured before
the first migration so later account fields can be added without swapping user
tables. See [the user-model decision](docs/adr/0001-start-with-an-extensible-user-model.md).

Overlap calculations and confirmed saves live in `scheduling/services.py`,
shared by the Django pages and later API endpoints. Commitments belong to a
user through their source. The scheduling admin is read-only; changes use the
application forms and their warning flow.

See [the agreed scope](docs/project_spec.md) and [domain glossary](GLOSSARY.md).
Setup references: [Django authentication](https://docs.djangoproject.com/en/6.1/topics/auth/default/),
[Django PostgreSQL requirements](https://docs.djangoproject.com/en/6.1/ref/databases/#postgresql-notes),
and [Ubuntu PostgreSQL installation](https://ubuntu.com/server/docs/how-to/databases/install-postgresql/).

## Scheduling chatbot

The read-only assistant is available at `/chat/` and in the **Ask my schedule**
panel. Configure a Groq Free-tier API key in `.env` and restart Django to enable
answers. ChatGPT Plus does not cover this API. See [chat setup and architecture](docs/chat_assistant.md)
for configuration, privacy, free-quota limits, and the rehearsal checklist.

## Google and GitHub sign-in

Social sign-in can create accounts for demo participants. Configure provider client
IDs and secrets, run `uv run python manage.py migrate`, and restart the app. See
[provider registration and exact callback URLs](docs/social_auth.md). Existing
username/password login stays available; provider buttons appear when configured.
