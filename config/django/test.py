"""PostgreSQL integration tests in Django's separate disposable test database."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-secret-key")

from .base import *  # noqa: E402, F403


PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
