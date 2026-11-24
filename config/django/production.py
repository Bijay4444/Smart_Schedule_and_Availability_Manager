"""Production: process environment only, explicit credentials, HTTPS defaults."""

from copy import deepcopy

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


if DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG must be false in production.")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY to a strong, unique production secret of at least 50 characters.")
if not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Set DJANGO_ALLOWED_HOSTS to explicit deployment hostnames; '*' is not allowed in production.")

# Do not inherit the developer's socket, OS username, or unnamed database.
if not env.str("DATABASE_URL", default="").strip():
    required_database_values = ("PGDATABASE", "PGUSER", "PGHOST", "PGPASSWORD")
    if any(not env.str(name, default="").strip() for name in required_database_values):
        raise ImproperlyConfigured("Set DATABASE_URL or all of PGDATABASE, PGUSER, PGHOST, and PGPASSWORD for production.")
if any(not DATABASES["default"].get(name) for name in ("NAME", "USER", "HOST", "PASSWORD")):
    raise ImproperlyConfigured("Production PostgreSQL needs an explicit database name, user, host, and password.")

DATABASES = deepcopy(DATABASES)
DATABASES["default"].setdefault("OPTIONS", {}).setdefault("sslmode", "require")

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=True)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=3600)
