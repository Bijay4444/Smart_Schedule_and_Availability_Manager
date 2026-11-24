"""Shared Django settings used by every environment."""

import getpass
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import env


BASE_DIR = Path(__file__).resolve().parents[2]

SECRET_KEY = env.str("DJANGO_SECRET_KEY", default="").strip()
if not SECRET_KEY:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY in the environment (or .env for local development)."
    )

DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = [
    host.strip()
    for host in env.list(
        "DJANGO_ALLOWED_HOSTS", default=[]
    )
    if host.strip()
]

# Profiles choose different defaults; integrations still belong in the shared base.
CSRF_TRUSTED_ORIGINS = [value.strip() for value in env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[]) if value.strip()]
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = env.bool("DJANGO_SESSION_COOKIE_SECURE", default=False)
CSRF_COOKIE_SECURE = env.bool("DJANGO_CSRF_COOKIE_SECURE", default=False)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=False)
# Stateless process liveness must also work on the container's internal HTTP port.
SECURE_REDIRECT_EXEMPT = [r"^healthz/$"]
# Enable only after verifying the deployment proxy strips/replaces client headers.
SECURE_PROXY_SSL_HEADER = (
    ("HTTP_X_FORWARDED_PROTO", "https")
    if env.bool("DJANGO_TRUST_X_FORWARDED_PROTO", default=False) else None
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "accounts.apps.AccountsConfig",
    "core.apps.CoreConfig",
    "scheduling.apps.SchedulingConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

if env.str("DATABASE_URL", default="").strip():
    database = env.db_url("DATABASE_URL")
else:
    database = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env.str("PGDATABASE", default="") or "smart_schedule",
        "USER": env.str("PGUSER", default="") or getpass.getuser(),
        "PASSWORD": env.str("PGPASSWORD", default=""),
        "HOST": env.str("PGHOST", default=""),
        "PORT": env.str("PGPORT", default="") or "5432",
    }
if database.get("ENGINE") != "django.db.backends.postgresql":
    raise ImproperlyConfigured("This project requires a PostgreSQL database.")
# These can supplement a URL, including its existing query-string options.
for variable, option in (("PGSSLMODE", "sslmode"), ("PGSSLROOTCERT", "sslrootcert")):
    value = env.str(variable, default="").strip()
    if value:
        database.setdefault("OPTIONS", {})[option] = value
DATABASES = {"default": database}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Halifax"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = False
WHITENOISE_USE_FINDERS = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Import integration settings from config.settings here when integrations are added.
