"""PostgreSQL integration tests in Django's separate disposable test database."""

import os
from pathlib import Path

from config.env import env

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")
env.read_env(Path(__file__).resolve().parents[2] / ".env", overwrite=False)

from .base import *  # noqa: E402, F403


PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
DEBUG = False
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
SECURE_PROXY_SSL_HEADER = None
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
WHITENOISE_AUTOREFRESH = True
WHITENOISE_USE_FINDERS = True
