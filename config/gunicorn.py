"""Container server defaults; deployment can tune capacity through environment."""

import os


bind = f"0.0.0.0:{int(os.environ.get('PORT', '8000'))}"
workers = int(os.environ.get("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.environ.get("GUNICORN_THREADS", "2"))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))
graceful_timeout = 30
worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
capture_output = True
# Exclude query strings, cookies, and authentication headers from access logs.
access_log_format = '%(h)s %(m)s %(U)s %(s)s %(L)s'
# Do not implicitly trust forwarded-protocol headers. Django's separate proxy
# setting is enabled only after verifying the Azure ingress configuration.
forwarded_allow_ips = ""
