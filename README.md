# Smart Schedule and Availability Manager

A Django application for people balancing classes, multiple jobs, and personal
commitments. It currently includes login/logout, private commitment sources,
and one-time commitment creation, editing, and deletion, including overnight
entries and conflict warnings.

## Current workflow

Open <http://127.0.0.1:8000/commitments/> after signing in:

1. Add a source such as Classes, Job A, or Personal and choose its color.
2. Add a one-time commitment with explicit start and end dates/times.
3. For overnight work, set the end to the following date.
4. If it overlaps another commitment, review the warning and explicitly confirm
   before saving. Overlaps remain marked on the list.
5. Edit a commitment or use its separate delete-confirmation page.

Times use Halifax time. Forms reject ambiguous/nonexistent daylight-saving
clock times. Recurring forms, working windows, availability calculation, and
the weekly calendar are upcoming increments in the
[development checklist](docs/development_checklist.md).

The recurring database foundation is now installed: stable series, dated
revisions, selected weekdays, and one-off exception storage. Backend services
now create/edit/end series, cancel/reschedule occurrences, and generate bounded
occurrences with automatic DST resolution and explicit review issues. Recurring
forms and conflict integration are next. Sources can be archived through the
service layer; archived commitments still block time and remain editable.
Source-management buttons are not yet provided. See the
[database design](docs/database_design.md) for the approved schema and boundaries.
The [recurrence service guide](docs/recurrence_services.md) explains the backend
interfaces, time calculations, and tests.

## What is installed

- Python 3.13 is selected by `.python-version` and managed by `uv`.
- Django provides the application, templates, admin, sessions, and authentication.
- Psycopg is the PostgreSQL driver. Its binary distribution avoids a local C
  compiler and PostgreSQL development-library requirement.
- django-environ reads typed environment values and loads the project-root `.env`.
- pytest and pytest-django provide the development test runner and Django test
  database integration.

Exact resolved versions are recorded in `uv.lock`. REST Framework will be added
when API work begins. Bootstrap CSS currently loads from a pinned CDN URL; no
Node.js build is needed. The Bootstrap styling requires an internet connection.

## Local setup in WSL

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

Django settings automatically load the project-root `.env`. Environment variables
already set by your shell or deployment take precedence. Keep personal settings
in `.env`; `.env.example` is the shareable template.

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

`config/django/base.py` contains the shared Django configuration and loads `.env`
before reading values through the shared `env` object in `config/env.py`.
`manage.py` defaults to `config.django.local`; WSGI and ASGI default to
`config.django.production`. Each imports the same base settings, and neither
currently needs overrides. Set `DJANGO_SETTINGS_MODULE` in the process environment
or use `manage.py --settings=...` to choose a different module. Set this variable
before Django starts; putting it only in `.env` is too late to select the module.

pytest defaults to `config.django.test`, which supplies a test-only secret when
none is set, keeps PostgreSQL as its backend, and speeds up password hashing. These test
overrides do not affect the local or production modules.

Future third-party settings belong in `config/settings/<integration>.py` and must
be imported at the end of `base.py`, so every environment sees them. Enable
optional integrations using an environment flag that defaults to false, and
require their credentials only when enabled. The package is currently empty
because no such integrations are configured.

Production uses the same environment variables as local development. Supply a
deployment secret, set `DJANGO_DEBUG=0`, and provide deployment-specific
`DJANGO_ALLOWED_HOSTS` and PostgreSQL values. The module name alone does not
configure deployment security, HTTPS, or a production server.

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
