"""Validate the single-VM deployment without provisioning infrastructure."""

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

import pytest

from scripts.prepare_vm_deploy import ROOT, prepare_bundle


@pytest.fixture
def bundle(tmp_path):
    return prepare_bundle(tmp_path / 'bundle', 'schedule.example.test', 'smart-schedule:vm-test')


def test_bundle_has_private_independent_credentials_and_does_not_rotate_them(bundle):
    before = (bundle / '.env').read_bytes()
    values = dict(line.split('=', 1) for line in before.decode().splitlines())
    assert len(values['DJANGO_SECRET_KEY']) >= 50
    assert len(values['POSTGRES_PASSWORD']) >= 32
    assert values['DJANGO_SECRET_KEY'] != values['POSTGRES_PASSWORD']
    assert stat.S_IMODE(bundle.stat().st_mode) == 0o700
    assert stat.S_IMODE((bundle / '.env').stat().st_mode) == 0o600
    assert stat.S_IMODE((bundle / 'deploy.sh').stat().st_mode) == 0o700
    assert (bundle / 'compose.yaml').is_file()
    with pytest.raises(ValueError, match='already exists'):
        prepare_bundle(bundle, 'other.example.test', 'smart-schedule:new-release')
    assert (bundle / '.env').read_bytes() == before


@pytest.mark.parametrize('hostname', ['https://demo.test', '*', 'demo.test:443', 'demo.test\nrespond hello', 'demo.test/path', '-bad.test', '127.0.0.1;whoami', '127.0.0.1'])
def test_bundle_rejects_hostnames_that_could_change_caddy_configuration(tmp_path, hostname):
    with pytest.raises(ValueError, match='DNS hostname'):
        prepare_bundle(tmp_path / 'bundle', hostname, 'smart-schedule:test')
    assert not (tmp_path / 'bundle').exists()


@pytest.mark.parametrize('image', ['smart-schedule', 'image:tag\nBAD=1', 'image:$(whoami)', 'image:tag with spaces'])
def test_bundle_requires_an_explicit_safe_image_tag(tmp_path, image):
    with pytest.raises(ValueError, match='image tag'):
        prepare_bundle(tmp_path / 'bundle', 'demo.test', image)


@pytest.fixture
def fake_docker(tmp_path, monkeypatch):
    executable = tmp_path / 'docker'
    executable.write_text(
        f'#!{sys.executable}\n'
        'import json,os,sys\n'
        'args=sys.argv[1:]\n'
        'if os.environ.get("ASSERT_PRIVATE_ENV"):\n'
        '    assert not any(k in os.environ for k in ["APP_HOST","APP_HOST_ALIAS","APP_IMAGE","DJANGO_SECRET_KEY","POSTGRES_PASSWORD","GROQ_API_KEY","GROQ_MODEL","GOOGLE_CLIENT_ID","GOOGLE_CLIENT_SECRET","GITHUB_CLIENT_ID","GITHUB_CLIENT_SECRET"])\n'
        'with open(os.environ["DOCKER_CALLS"],"a") as f: f.write(json.dumps(args)+"\\n")\n'
        'if os.environ.get("FAIL_DOCKER_ON") and os.environ["FAIL_DOCKER_ON"] in " ".join(args): sys.exit(7)\n'
        'if "pg_dump" in " ".join(args): sys.stdout.buffer.write(b"PGDMP-test-backup")\n'
    )
    executable.chmod(0o700)
    calls = tmp_path / 'docker-calls.jsonl'
    monkeypatch.setenv('PATH', f'{tmp_path}:{os.environ["PATH"]}')
    monkeypatch.setenv('DOCKER_CALLS', str(calls))
    return calls


def commands(path):
    return [' '.join(json.loads(line)) for line in path.read_text().splitlines()]


def test_failed_migration_never_starts_web_or_proxy(bundle, fake_docker, monkeypatch):
    monkeypatch.setenv('FAIL_DOCKER_ON', 'run --rm --no-deps migrate')
    result = subprocess.run(['sh', str(bundle / 'deploy.sh')], capture_output=True, text=True)
    assert result.returncode == 7
    calls = commands(fake_docker)
    assert any('stop proxy web' in call for call in calls)
    assert not any('up -d --wait --no-deps web' in call or 'up -d --wait --no-deps proxy' in call for call in calls)
    assert not (bundle / '.deploy-lock').exists()


def test_successful_deployment_verifies_migrations_before_proxy_starts(bundle, fake_docker):
    subprocess.run(['sh', str(bundle / 'deploy.sh')], check=True, capture_output=True)
    calls = commands(fake_docker)
    migrate = next(i for i, call in enumerate(calls) if 'run --rm --no-deps migrate' in call)
    verify = next(i for i, call in enumerate(calls) if 'manage.py migrate --check' in call)
    publish = next(i for i, call in enumerate(calls) if 'up -d --wait --no-deps proxy' in call)
    assert migrate < verify < publish


def test_deployment_does_not_inherit_local_secrets_or_host_overrides(bundle, fake_docker, monkeypatch):
    monkeypatch.setenv('ASSERT_PRIVATE_ENV', '1')
    for name in ('APP_HOST', 'APP_HOST_ALIAS', 'APP_IMAGE', 'DJANGO_SECRET_KEY', 'POSTGRES_PASSWORD', 'GROQ_API_KEY', 'GROQ_MODEL', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'GITHUB_CLIENT_ID', 'GITHUB_CLIENT_SECRET'):
        monkeypatch.setenv(name, 'development-value')
    subprocess.run(['sh', str(bundle / 'deploy.sh')], check=True, capture_output=True)
    subprocess.run(['sh', str(bundle / 'backup.sh')], check=True, capture_output=True)


def test_deployment_refuses_a_concurrent_operator(bundle, fake_docker):
    (bundle / '.deploy-lock').mkdir()
    result = subprocess.run(['sh', str(bundle / 'deploy.sh')], capture_output=True)
    assert result.returncode != 0
    assert not fake_docker.exists()


def test_backup_is_private_and_failed_dump_is_not_reported_as_valid(bundle, fake_docker, monkeypatch):
    subprocess.run(['sh', str(bundle / 'backup.sh')], check=True, capture_output=True)
    backups = list((bundle / 'backups').glob('*.dump'))
    assert len(backups) == 1
    assert backups[0].read_bytes() == b'PGDMP-test-backup'
    assert stat.S_IMODE(backups[0].stat().st_mode) == 0o600
    monkeypatch.setenv('FAIL_DOCKER_ON', 'pg_dump')
    assert subprocess.run(['sh', str(bundle / 'backup.sh')], capture_output=True).returncode != 0
    assert list((bundle / 'backups').glob('*.dump')) == backups
    assert not list((bundle / 'backups').glob('.backup.*'))


def test_rendered_compose_only_exposes_proxy_and_keeps_secure_django_settings(bundle):
    if not shutil.which('docker'):
        pytest.skip('Docker CLI with Compose is needed to render configuration')
    result = subprocess.run(['docker', 'compose', '--env-file', str(bundle / '.env'), '-f', str(bundle / 'compose.yaml'), '--profile', 'ops', 'config', '--format', 'json'], check=True, capture_output=True, text=True)
    config = json.loads(result.stdout)
    for name in ('db', 'web', 'migrate'):
        assert not config['services'][name].get('ports')
    assert {str(p['published']) for p in config['services']['proxy']['ports']} == {'80', '443'}
    environment = config['services']['web']['environment']
    assert environment['DJANGO_DEBUG'] == 'false'
    assert environment['DJANGO_SECURE_SSL_REDIRECT'] == 'true'
    assert environment['DJANGO_SESSION_COOKIE_SECURE'] == 'true'
    assert environment['DJANGO_ALLOWED_HOSTS'] == 'schedule.example.test'
    assert environment['WEB_CONCURRENCY'] == '1'
    assert config['networks']['backend']['internal'] is True
    assert config['services']['web']['pull_policy'] == 'never'


def test_custom_domain_alias_configures_both_django_and_caddy(bundle):
    if not shutil.which('docker'):
        pytest.skip('Docker CLI with Compose is needed to render configuration')
    with (bundle / '.env').open('a') as stream:
        stream.write('APP_HOST_ALIAS=original.example.test\n')
    environment = os.environ.copy()
    environment.pop('APP_HOST_ALIAS', None)
    result = subprocess.run(['docker', 'compose', '--env-file', str(bundle / '.env'), '-f', str(bundle / 'compose.yaml'), 'config', '--format', 'json'], env=environment, check=True, capture_output=True, text=True)
    config = json.loads(result.stdout)
    app = config['services']['web']['environment']
    assert app['DJANGO_ALLOWED_HOSTS'] == 'schedule.example.test,original.example.test'
    assert app['DJANGO_CSRF_TRUSTED_ORIGINS'] == 'https://schedule.example.test,https://original.example.test'
    assert config['services']['proxy']['environment']['APP_HOST_ALIAS'] == 'original.example.test'


def test_compiled_vm_uses_one_persistent_disk_key_auth_and_narrow_inbound_rules(tmp_path):
    binary = os.environ.get('BICEP_BIN') or shutil.which('bicep')
    if not binary:
        pytest.skip('Set BICEP_BIN to validate infrastructure compilation')
    output = tmp_path / 'vm.json'
    subprocess.run([binary, 'build', str(ROOT / 'infra/azure/vm.bicep'), '--outfile', str(output)], check=True, capture_output=True)
    template = json.loads(output.read_text())
    connection = template['outputs']['connection']['value']
    assert set(connection) == {'hostname', 'publicAddress', 'vmName', 'sshUser'}
    # ARM must unwrap each module output's value instead of returning the
    # module's complete {type, value} descriptors as the connection fields.
    assert connection['hostname'].endswith('.outputs.hostname.value]')
    module = next(r for r in template['resources'] if r['type'] == 'Microsoft.Resources/deployments')
    resources = module['properties']['template']['resources']
    vm = next(r for r in resources if r['type'] == 'Microsoft.Compute/virtualMachines')
    disk = vm['properties']['storageProfile']['osDisk']
    assert disk['diskSizeGB'] == 32
    assert disk['managedDisk']['storageAccountType'] == 'StandardSSD_LRS'
    assert 'diffDiskSettings' not in disk
    assert disk['deleteOption'] == 'Detach'
    assert vm['properties']['osProfile']['linuxConfiguration']['disablePasswordAuthentication'] is True
    firewall = next(r for r in resources if r['type'] == 'Microsoft.Network/networkSecurityGroups')
    rules = {r['name']: r['properties'] for r in firewall['properties']['securityRules']}
    assert rules['OwnerSSH']['destinationPortRange'] == '22'
    assert rules['OwnerSSH']['sourceAddressPrefix'] == "[parameters('sshSourceCidr')]"
    assert rules['PublicWeb']['destinationPortRanges'] == ['80', '443']
    assert 'defaultValue' not in template['parameters']['sshSourceCidr']
    assert not any(r['type'].startswith(('Microsoft.Web/', 'Microsoft.ContainerRegistry/', 'Microsoft.DBforPostgreSQL/')) for r in resources)
