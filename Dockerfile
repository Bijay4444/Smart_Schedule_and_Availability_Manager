# syntax=docker/dockerfile:1
ARG PYTHON_VERSION=3.13.15
FROM python:${PYTHON_VERSION}-slim-bookworm AS python-base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=America/Halifax
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app

FROM python-base AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.13 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY accounts ./accounts
COPY assistant ./assistant
COPY config ./config
COPY core ./core
COPY scheduling ./scheduling
COPY templates ./templates
COPY static ./static
COPY docker/healthcheck.py ./docker/healthcheck.py
COPY manage.py ./

# Static collection does not use a database or any deployment credentials.
# The base settings use the same manifest backend as production. This placeholder
# exists only for this build command and is never a runtime secret/default.
RUN DJANGO_SETTINGS_MODULE=config.django.base \
    DJANGO_SECRET_KEY=static-build-only-not-a-runtime-secret \
    .venv/bin/python manage.py collectstatic --noinput

FROM python-base AS runtime
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --home-dir /app \
        --shell /usr/sbin/nologin app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=config.django.production \
    PORT=8000
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD ["python", "docker/healthcheck.py"]
CMD ["gunicorn", "--config", "python:config.gunicorn", "config.wsgi:application"]
