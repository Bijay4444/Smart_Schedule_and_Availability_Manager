"""Dependency-free liveness probe shared by Docker and Compose."""

import os
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen


try:
    port = int(os.environ.get("PORT", "8000"))
    # The socket is loopback, but production ALLOWED_HOSTS usually contains only
    # the public domain. Preserve host validation rather than adding a wildcard.
    host = next((value.strip().lstrip(".") for value in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost").split(",") if value.strip()), "localhost")
    request = Request(f"http://127.0.0.1:{port}/healthz/", headers={"Host": host})
    with urlopen(request, timeout=3) as response:
        healthy = response.status == 200 and response.read() == b"ok\n"
except (OSError, URLError, ValueError):
    healthy = False
sys.exit(0 if healthy else 1)
