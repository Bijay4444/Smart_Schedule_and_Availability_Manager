"""Infrastructure behavior without touching the application database."""

import gzip
from io import BytesIO
from pathlib import Path
import runpy
from urllib.parse import urlsplit
import urllib.request

import pytest
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.management import call_command
from django.test import Client, override_settings
from django.urls import reverse


@pytest.mark.parametrize("method", ["get", "head"])
def test_health_is_public_stateless_and_does_not_access_database(client, method):
    # pytest's default database blocker proves this endpoint never connects.
    response = getattr(client, method)(reverse("healthz"))
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    assert response["Content-Type"] == "text/plain"
    assert response.content == (b"ok\n" if method == "get" else b"")
    assert not response.cookies


def test_health_rejects_writes(client):
    assert client.post(reverse("healthz")).status_code == 405


@override_settings(SECURE_SSL_REDIRECT=True)
def test_only_liveness_bypasses_https_redirect(client):
    assert client.get(reverse("healthz")).status_code == 200
    response = client.get(reverse("login"))
    assert response.status_code == 301
    assert response.url.startswith("https://")


@override_settings(ALLOWED_HOSTS=["schedule.example.test"], SECURE_SSL_REDIRECT=True)
def test_container_probe_works_when_only_the_public_hostname_is_allowed(monkeypatch):
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", " schedule.example.test,alternate.example.test ")

    def respond_with_django(request, timeout):
        response = Client().get(urlsplit(request.full_url).path, HTTP_HOST=request.get_header("Host"))
        stream = BytesIO(response.content)
        stream.status = response.status_code
        return stream

    monkeypatch.setattr(urllib.request, "urlopen", respond_with_django)
    with pytest.raises(SystemExit) as result:
        runpy.run_path(Path(__file__).resolve().parents[1] / "docker/healthcheck.py", run_name="__main__")
    assert result.value.code == 0


def test_production_static_assets_are_hashed_compressed_and_served_without_runserver(tmp_path):
    with override_settings(
        DEBUG=False,
        STATIC_ROOT=tmp_path / "staticfiles",
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
        },
        WHITENOISE_AUTOREFRESH=False,
        WHITENOISE_USE_FINDERS=False,
    ):
        call_command("collectstatic", interactive=False, verbosity=0)
        url = staticfiles_storage.url("css/app.css")
        assert url.startswith("/static/css/app.") and url.endswith(".css")
        response = Client().get(url, HTTP_ACCEPT_ENCODING="gzip")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/css")
        assert response["Content-Encoding"] == "gzip"
        assert "immutable" in response["Cache-Control"]
        assert b"--ink:" in gzip.decompress(b"".join(response.streaming_content))
        response.close()
