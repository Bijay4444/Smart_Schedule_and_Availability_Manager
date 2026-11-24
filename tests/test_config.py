"""Exercise settings startup in fresh processes, without the developer's .env."""

import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


PRODUCTION_ENV = {
    "DJANGO_SECRET_KEY": "test-production-key-" + "0123456789abcdef" * 4,
    "DJANGO_ALLOWED_HOSTS": "schedule.example.test",
    "PGDATABASE": "production_schedule",
    "PGUSER": "production_user",
    "PGPASSWORD": "example-database-password",
    "PGHOST": "db.example.test",
}


@pytest.fixture
def load_settings(tmp_path):
    project_root = Path(__file__).resolve().parents[1]
    shutil.copytree(
        project_root / "config",
        tmp_path / "config",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    working_directory = tmp_path / "elsewhere"
    working_directory.mkdir()

    def load(module, *, dotenv=None, environment=None, check=True):
        if dotenv is not None:
            (tmp_path / ".env").write_text(dotenv)
        process_env = os.environ.copy()
        for name in list(process_env):
            if name.startswith("DJANGO_") or name in {
                "DATABASE_URL", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGHOST", "PGPORT",
                "PGSSLMODE", "PGSSLROOTCERT",
            }:
                del process_env[name]
        process_env["PYTHONPATH"] = str(tmp_path)
        process_env.update(environment or {})
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import json, sys; from django.conf import Settings; "
                "settings = Settings(sys.argv[1]); "
                "print(json.dumps({name: getattr(settings, name) for name in "
                "['BASE_DIR', 'SECRET_KEY', 'DEBUG', 'ALLOWED_HOSTS', 'DATABASES', "
                "'TEMPLATES', 'STATICFILES_DIRS', 'STATIC_ROOT', 'PASSWORD_HASHERS', "
                "'CSRF_TRUSTED_ORIGINS', 'SECURE_SSL_REDIRECT', 'SESSION_COOKIE_SECURE', "
                "'CSRF_COOKIE_SECURE', 'SECURE_HSTS_SECONDS', 'SECURE_HSTS_INCLUDE_SUBDOMAINS', "
                "'SECURE_HSTS_PRELOAD', 'SECURE_PROXY_SSL_HEADER']}, "
                "default=str))",
                module,
            ],
            cwd=working_directory,
            env=process_env,
            capture_output=True,
            text=True,
            check=check,
            timeout=15,
        )
        return json.loads(result.stdout) if check else result

    return load


def test_local_loads_project_dotenv_from_any_working_directory(load_settings, tmp_path):
    settings = load_settings(
        "config.django.local",
        dotenv=(
            "DJANGO_SECRET_KEY=dotenv-secret\n"
            "DJANGO_DEBUG=true\n"
            "DJANGO_ALLOWED_HOSTS= localhost, example.test, ,\n"
            "PGDATABASE=custom_schedule\nPGUSER=custom_user\n"
            "PGPASSWORD=sample-password\nPGHOST=db.example.test\nPGPORT=5433\n"
        ),
    )

    assert settings["SECRET_KEY"] == "dotenv-secret"
    assert settings["DEBUG"] is True
    assert settings["ALLOWED_HOSTS"] == ["localhost", "example.test"]
    assert settings["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "custom_schedule",
        "USER": "custom_user",
        "PASSWORD": "sample-password",
        "HOST": "db.example.test",
        "PORT": "5433",
    }
    assert settings["BASE_DIR"] == str(tmp_path)
    assert settings["TEMPLATES"][0]["DIRS"] == [str(tmp_path / "templates")]
    assert settings["STATICFILES_DIRS"] == [str(tmp_path / "static")]
    assert settings["STATIC_ROOT"] == str(tmp_path / "staticfiles")


def test_process_environment_takes_precedence_over_dotenv(load_settings):
    settings = load_settings(
        "config.django.local",
        dotenv="DJANGO_SECRET_KEY=dotenv-secret\nDJANGO_DEBUG=1\nPGHOST=local-db\n",
        environment={
            "DJANGO_SECRET_KEY": "environment-secret",
            "DJANGO_DEBUG": "false",
            "PGHOST": "deployment-db",
        },
    )

    assert settings["SECRET_KEY"] == "environment-secret"
    assert settings["DEBUG"] is False
    assert settings["DATABASES"]["default"]["HOST"] == "deployment-db"


@pytest.mark.parametrize("blank_postgres_values", [False, True])
def test_defaults_work_without_dotenv(load_settings, blank_postgres_values):
    environment = {"DJANGO_SECRET_KEY": "environment-secret"}
    if blank_postgres_values:
        environment.update(PGDATABASE="", PGUSER="", PGPORT="")
    settings = load_settings("config.django.local", environment=environment)

    assert settings["DEBUG"] is True
    assert settings["ALLOWED_HOSTS"] == ["localhost", "127.0.0.1", "[::1]"]
    assert settings["DATABASES"]["default"] == {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "smart_schedule",
        "USER": getpass.getuser(),
        "PASSWORD": "",
        "HOST": "",
        "PORT": "5432",
    }


@pytest.mark.parametrize("secret", [None, ""])
def test_application_settings_require_a_nonempty_secret(load_settings, secret):
    result = load_settings(
        "config.django.production",
        environment={} if secret is None else {"DJANGO_SECRET_KEY": secret},
        check=False,
    )

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
    assert "Set DJANGO_SECRET_KEY" in result.stderr


def test_test_settings_use_postgres_without_dotenv_or_secret(load_settings):
    settings = load_settings("config.django.test")

    assert settings["SECRET_KEY"] == "test-only-secret-key"
    assert settings["DATABASES"] == {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": "smart_schedule",
            "USER": getpass.getuser(),
            "PASSWORD": "",
            "HOST": "",
            "PORT": "5432",
        }
    }
    assert settings["PASSWORD_HASHERS"] == ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.mark.parametrize("module", ["base", "production"])
def test_shared_and_production_profiles_do_not_load_a_local_dotenv(load_settings, module):
    result = load_settings(
        f"config.django.{module}",
        dotenv="DJANGO_SECRET_KEY=local-secret\nDJANGO_DEBUG=true\nPGHOST=local-db\n",
        check=False,
    )
    assert result.returncode != 0
    assert "Set DJANGO_SECRET_KEY" in result.stderr


def test_production_defaults_are_secure_and_ignore_local_dotenv(load_settings):
    settings = load_settings(
        "config.django.production",
        environment=PRODUCTION_ENV,
        dotenv="DJANGO_DEBUG=true\nPGHOST=local-db\nDJANGO_SECURE_SSL_REDIRECT=false\n",
    )
    assert settings["DEBUG"] is False
    assert settings["SECRET_KEY"] == PRODUCTION_ENV["DJANGO_SECRET_KEY"]
    assert settings["ALLOWED_HOSTS"] == ["schedule.example.test"]
    assert settings["DATABASES"]["default"]["HOST"] == "db.example.test"
    assert settings["DATABASES"]["default"]["OPTIONS"] == {"sslmode": "require"}
    assert settings["SECURE_SSL_REDIRECT"] is True
    assert settings["SESSION_COOKIE_SECURE"] is True
    assert settings["CSRF_COOKIE_SECURE"] is True
    assert settings["SECURE_HSTS_SECONDS"] == 3600
    assert settings["SECURE_PROXY_SSL_HEADER"] is None


@pytest.mark.parametrize("changes,message", [
    ({"DJANGO_DEBUG": "true"}, "DJANGO_DEBUG must be false"),
    ({"DJANGO_SECRET_KEY": "short-secret"}, "strong, unique production secret"),
    ({"DJANGO_SECRET_KEY": "x" * 64}, "strong, unique production secret"),
    ({"DJANGO_SECRET_KEY": "django-insecure-" + "1234567890" * 6}, "strong, unique production secret"),
    ({"DJANGO_ALLOWED_HOSTS": ""}, "explicit deployment hostnames"),
    ({"DJANGO_ALLOWED_HOSTS": "*,example.test"}, "explicit deployment hostnames"),
    ({"PGDATABASE": ""}, "Set DATABASE_URL or all of"),
    ({"PGUSER": ""}, "Set DATABASE_URL or all of"),
    ({"PGHOST": ""}, "Set DATABASE_URL or all of"),
    ({"PGPASSWORD": ""}, "Set DATABASE_URL or all of"),
])
def test_production_rejects_missing_or_unsafe_deployment_values(load_settings, changes, message):
    result = load_settings("config.django.production", environment=PRODUCTION_ENV | changes, check=False)
    assert result.returncode != 0
    assert message in result.stderr


def test_production_does_not_fall_back_to_local_database_credentials(load_settings):
    result = load_settings(
        "config.django.production",
        environment={name: value for name, value in PRODUCTION_ENV.items() if name.startswith("DJANGO_")},
        dotenv="PGDATABASE=local_db\nPGUSER=local_user\nPGHOST=local-db\nPGPASSWORD=local-password\n",
        check=False,
    )
    assert result.returncode != 0
    assert "Set DATABASE_URL or all of" in result.stderr


@pytest.mark.parametrize("module", ["local", "production"])
def test_database_url_wins_and_preserves_encoded_password_and_ssl_options(load_settings, module):
    settings = load_settings(f"config.django.{module}", environment=PRODUCTION_ENV | {
        "DATABASE_URL": "postgresql://url_user:encoded%40pass%3Aword@url-db.example.test:5433/url_database?sslmode=verify-full&connect_timeout=10",
    })
    database = settings["DATABASES"]["default"]
    assert database["NAME"] == "url_database"
    assert database["USER"] == "url_user"
    assert database["PASSWORD"] == "encoded@pass:word"
    assert database["HOST"] == "url-db.example.test"
    assert database["PORT"] == 5433
    assert database["OPTIONS"] == {"sslmode": "verify-full", "connect_timeout": 10}


def test_production_can_use_a_database_url_without_pg_fields(load_settings):
    settings = load_settings("config.django.production", environment={
        "DJANGO_SECRET_KEY": PRODUCTION_ENV["DJANGO_SECRET_KEY"],
        "DJANGO_ALLOWED_HOSTS": "schedule.example.test",
        "DATABASE_URL": "postgresql://url_user:encoded-pass@db.example.test/url_database",
    })
    assert settings["DATABASES"]["default"]["NAME"] == "url_database"
    assert settings["DATABASES"]["default"]["OPTIONS"]["sslmode"] == "require"


@pytest.mark.parametrize("url", ["sqlite:///database.sqlite3", "mysql://user:password@localhost/database"])
def test_non_postgresql_urls_fail_before_startup(load_settings, url):
    result = load_settings("config.django.local", environment={"DJANGO_SECRET_KEY": "local-secret", "DATABASE_URL": url}, check=False)
    assert result.returncode != 0
    assert "requires a PostgreSQL database" in result.stderr


@pytest.mark.parametrize("url", ["postgresql://user@localhost/database", "postgresql:///database"])
def test_production_url_must_not_leave_connection_credentials_implicit(load_settings, url):
    result = load_settings("config.django.production", environment=PRODUCTION_ENV | {"DATABASE_URL": url}, check=False)
    assert result.returncode != 0
    assert "explicit database name, user, host, and password" in result.stderr


def test_database_tls_variables_can_supplement_a_url(load_settings):
    settings = load_settings("config.django.production", environment=PRODUCTION_ENV | {
        "DATABASE_URL": "postgresql://user:password@db.example.test/database?connect_timeout=10",
        "PGSSLMODE": "verify-full", "PGSSLROOTCERT": "/certs/database-ca.pem",
    })
    assert settings["DATABASES"]["default"]["OPTIONS"] == {
        "connect_timeout": 10, "sslmode": "verify-full", "sslrootcert": "/certs/database-ca.pem",
    }


def test_production_proxy_trust_and_csrf_origins_are_explicit_options(load_settings):
    settings = load_settings("config.django.production", environment=PRODUCTION_ENV | {
        "DJANGO_TRUST_X_FORWARDED_PROTO": "true",
        "DJANGO_CSRF_TRUSTED_ORIGINS": " https://schedule.example.test, https://alternate.example.test, ,",
        "DJANGO_SECURE_HSTS_SECONDS": "86400",
        "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS": "true",
        "DJANGO_SECURE_HSTS_PRELOAD": "true",
    })
    assert settings["SECURE_PROXY_SSL_HEADER"] == ["HTTP_X_FORWARDED_PROTO", "https"]
    assert settings["CSRF_TRUSTED_ORIGINS"] == ["https://schedule.example.test", "https://alternate.example.test"]
    assert settings["SECURE_HSTS_SECONDS"] == 86400
    assert settings["SECURE_HSTS_INCLUDE_SUBDOMAINS"] is True
    assert settings["SECURE_HSTS_PRELOAD"] is True


def test_test_profile_keeps_test_only_security_defaults_and_local_database_loading(load_settings):
    settings = load_settings("config.django.test", dotenv=(
        "DJANGO_SECRET_KEY=local-secret\nDJANGO_DEBUG=true\nPGDATABASE=isolated_db\n"
        "DJANGO_SECURE_SSL_REDIRECT=true\nDJANGO_SESSION_COOKIE_SECURE=true\n"
        "DJANGO_CSRF_COOKIE_SECURE=true\nDJANGO_SECURE_HSTS_SECONDS=86400\n"
        "DJANGO_TRUST_X_FORWARDED_PROTO=true\n"
    ))
    assert settings["SECRET_KEY"] == "test-only-secret-key"
    assert settings["DATABASES"]["default"]["NAME"] == "isolated_db"
    assert settings["DEBUG"] is False
    assert settings["SECURE_SSL_REDIRECT"] is False
    assert settings["SESSION_COOKIE_SECURE"] is False
    assert settings["CSRF_COOKIE_SECURE"] is False
    assert settings["SECURE_HSTS_SECONDS"] == 0
    assert settings["SECURE_PROXY_SSL_HEADER"] is None
