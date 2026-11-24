"""Local development: optional project .env, debugging, and loopback hosts."""

from pathlib import Path

from config.env import env


env.read_env(Path(__file__).resolve().parents[2] / ".env", overwrite=False)

from .base import *  # noqa: E402, F403


DEBUG = env.bool("DJANGO_DEBUG", default=True)
ALLOWED_HOSTS = [
    value.strip() for value in env.list(
        "DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"]
    ) if value.strip()
]

# Local edits should work immediately without first running collectstatic.
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
