"""Exercise settings startup in fresh processes, without the developer's .env."""

import getpass
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


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
                "PGDATABASE", "PGUSER", "PGPASSWORD", "PGHOST", "PGPORT"
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
                "'TEMPLATES', 'STATICFILES_DIRS', 'STATIC_ROOT', 'PASSWORD_HASHERS']}, "
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


@pytest.mark.parametrize("module", ["base", "local", "production"])
def test_profiles_load_project_dotenv_from_any_working_directory(load_settings, tmp_path, module):
    settings = load_settings(
        f"config.django.{module}",
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
        "config.django.production",
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

    assert settings["DEBUG"] is False
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
