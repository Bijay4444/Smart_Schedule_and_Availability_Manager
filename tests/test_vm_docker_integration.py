"""Opt-in real Compose rehearsal: VM_TEST_IMAGE=<built tag> pytest this file.

Uses isolated disposable volumes, loopback ports and a Caddy local test CA.
Never accesses Azure or the development database. Requires Docker and curl.
"""

import json
import os
import re
import secrets
import socket
import subprocess
from urllib.parse import urlencode
import uuid

import pytest

from scripts.prepare_vm_deploy import prepare_bundle


pytestmark = pytest.mark.skipif(not os.environ.get('VM_TEST_IMAGE'), reason='Set VM_TEST_IMAGE to opt into the real Docker rehearsal')


def free_port():
    with socket.socket() as stream:
        stream.bind(('127.0.0.1', 0))
        return stream.getsockname()[1]


def test_https_login_isolation_persistence_and_backup_restore(tmp_path):
    project = 'schedule-rehearsal-' + uuid.uuid4().hex[:10]
    bundle = prepare_bundle(tmp_path / 'bundle', 'schedule.example.test', os.environ['VM_TEST_IMAGE'])
    http_port, https_port = free_port(), free_port()
    config = (bundle / 'compose.yaml').read_text().replace('"80:80", "443:443"', f'"127.0.0.1:{http_port}:80", "127.0.0.1:{https_port}:443"')
    (bundle / 'compose.yaml').write_text(config)
    caddy = (bundle / 'Caddyfile').read_text().replace('    encode', '    tls internal\n    encode')
    (bundle / 'Caddyfile').write_text(caddy)
    environment = os.environ | {'COMPOSE_PROJECT_NAME': project}
    for name in ('APP_HOST', 'APP_HOST_ALIAS', 'APP_IMAGE', 'DJANGO_SECRET_KEY', 'POSTGRES_PASSWORD'):
        environment.pop(name, None)
    base = ['docker', 'compose', '--env-file', str(bundle / '.env'), '-f', str(bundle / 'compose.yaml')]

    def compose(*args, input=None):
        return run([*base, *args], input=input)

    def run(command, input=None, timeout=300):
        result = subprocess.run(command, input=input, env=environment, cwd=bundle, text=True, capture_output=True, timeout=timeout)
        if result.returncode:
            pytest.fail(f'Container operation failed ({result.returncode}):\n{result.stdout[-4000:]}\n{result.stderr[-6000:]}')
        return result

    def shell(code):
        return compose('exec', '-T', 'web', 'python', 'manage.py', 'shell', input=code)

    try:
        run(['sh', str(bundle / 'deploy.sh')], timeout=420)
        root = tmp_path / 'root.crt'
        compose('cp', 'proxy:/data/caddy/pki/authorities/local/root.crt', str(root))
        cookies = tmp_path / 'cookies.txt'

        def request(path, data=None, extra_headers=()):
            url = f'https://schedule.example.test:{https_port}{path}'
            command = ['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '15',
                       '--cacert', str(root), '--resolve', f'schedule.example.test:{https_port}:127.0.0.1',
                       '-b', str(cookies), '-c', str(cookies), '-w', '\n%{http_code}']
            for header in extra_headers:
                command += ['-H', header]
            if data is not None:
                command += ['--data-binary', '@-', '-H', 'Content-Type: application/x-www-form-urlencoded', '-H', f'Referer: {url}']
            result = subprocess.run([*command, url], input=urlencode(data) if data is not None else None, text=True, capture_output=True, check=True)
            body, status = result.stdout.rsplit('\n', 1)
            return int(status), body

        assert request('/healthz/') == (200, 'ok\n')
        # Client-provided forwarded-protocol headers must not defeat the proxy.
        assert request('/accounts/login/', extra_headers=['X-Forwarded-Proto: http'])[0] == 200
        redirect = subprocess.run(['curl', '--noproxy', '*', '--silent', '--show-error', '--max-time', '15', '-D', '-', '-o', '/dev/null', '-H', 'Host: schedule.example.test', f'http://127.0.0.1:{http_port}/accounts/login/'], text=True, check=True, capture_output=True).stdout
        assert '308' in redirect and 'Location: https://schedule.example.test/accounts/login/' in redirect
        password = secrets.token_urlsafe(24)
        shell('''from django.contrib.auth import get_user_model
from scheduling.models import CommitmentSource, Commitment
from datetime import datetime, UTC, timedelta
User = get_user_model()
owner = User.objects.create_user(username='rehearsal', password=''' + repr(password) + ''')
other = User.objects.create_user(username='other')
for user, title in [(owner, 'Rehearsal visible'), (other, 'Other private title')]:
    source = CommitmentSource.objects.create(owner=user, name=title)
    now = datetime.now(UTC)
    Commitment.objects.create(source=source, title=title, starts_at=now, ends_at=now+timedelta(hours=1))
''')
        status, html = request('/accounts/login/')
        assert status == 200
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', html)[1]
        assert request('/accounts/login/', {'username': 'rehearsal', 'password': password, 'csrfmiddlewaretoken': token})[0] == 302
        status, commitments = request('/commitments/')
        assert status == 200 and 'Rehearsal visible' in commitments and 'Other private title' not in commitments
        assert request('/week/')[0] == 200
        asset = re.search(r'href="(/static/css/app\.[^"]+\.css)"', commitments)[1]
        assert request(asset)[0] == 200

        subprocess.run(['sh', str(bundle / 'backup.sh')], env=environment, check=True, capture_output=True, text=True, timeout=120)
        backup = next((bundle / 'backups').glob('*.dump'))
        assert backup.read_bytes().startswith(b'PGDMP')
        # Recreate the DB container while retaining the managed-volume analogue.
        compose('stop', 'proxy', 'web')
        compose('up', '-d', '--wait', '--force-recreate', 'db')
        compose('up', '-d', '--wait', 'web', 'proxy')
        assert 'Rehearsal visible' in request('/commitments/')[1]

        # Restore to a NEW disposable database, never over the source database.
        compose('exec', '-T', 'db', 'createdb', '-U', 'smart_schedule', 'restore_check')
        subprocess.run([*base, 'exec', '-T', 'db', 'pg_restore', '--exit-on-error', '--no-owner', '--no-acl', '-U', 'smart_schedule', '-d', 'restore_check'], input=backup.read_bytes(), env=environment, check=True, capture_output=True, timeout=120)
        count = compose('exec', '-T', 'db', 'psql', '-U', 'smart_schedule', '-d', 'restore_check', '-Atc', 'SELECT count(*) FROM scheduling_commitment;').stdout.strip()
        assert count == '2'
        published = json.loads(compose('config', '--format', 'json').stdout)
        assert not published['services']['db'].get('ports')
        assert not published['services']['web'].get('ports')
    finally:
        # The random project name scopes deletion to this rehearsal's volumes.
        subprocess.run([*base, 'down', '--volumes', '--remove-orphans'], env=environment, capture_output=True, timeout=120)
