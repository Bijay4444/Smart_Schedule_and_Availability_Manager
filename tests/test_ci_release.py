"""Check release integrity and deployment failure behavior without cloud access."""

import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest

from scripts.package_vm_release import FILES, ROOT, package


spec = importlib.util.spec_from_file_location('vm_install_release', ROOT / 'docker/vm/install_release.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
COMMIT = 'a' * 40


@pytest.fixture
def release(tmp_path):
    archive = tmp_path / 'image.tar'
    archive.write_bytes(b'fake image content; Docker operations are stubbed')
    output = tmp_path / 'incoming'
    package(archive, COMMIT, output)
    return output


@pytest.fixture
def live(tmp_path):
    target = tmp_path / 'live'
    target.mkdir()
    (target / '.env').write_text('APP_HOST=schedule.example.test\nAPP_HOST_ALIAS=azure.example.test\nAPP_IMAGE=smart-schedule:previous\nDJANGO_SECRET_KEY=private-existing-secret\nPOSTGRES_PASSWORD=private-existing-password\n')
    (target / '.env').chmod(0o600)
    for name in installer.DEPLOYMENT_FILES:
        (target / name).write_text('old deployment configuration\n')
    return target


def test_package_only_contains_allowlisted_code_and_image(release):
    assert {p.name for p in release.iterdir()} == {'release.json', 'app-image.tar', *FILES}
    manifest = installer.validate(release, COMMIT)
    assert manifest['image'] == 'smart-schedule:' + COMMIT
    assert not (release / '.env').exists()


@pytest.mark.parametrize('commit', ['main', '../bad', 'a' * 39, 'a' * 40 + ';whoami'])
def test_invalid_commit_never_creates_a_release(tmp_path, commit):
    with pytest.raises(ValueError, match='commit'):
        package(tmp_path / 'missing.tar', commit, tmp_path / 'release')
    assert not (tmp_path / 'release').exists()


@pytest.mark.parametrize('tampering', ['image', 'path', 'env', 'commit'])
def test_tampering_is_rejected_before_backup_or_live_mutation(release, live, monkeypatch, tampering):
    before = {p.name: p.read_bytes() for p in live.iterdir()}
    if tampering == 'image':
        (release / 'app-image.tar').write_bytes(b'changed image')
    elif tampering == 'env':
        (release / '.env').write_text('must not be uploaded')
    else:
        manifest = json.loads((release / 'release.json').read_text())
        if tampering == 'path':
            manifest['files']['../.env'] = '0' * 64
        else:
            manifest['commit'] = 'b' * 40
        (release / 'release.json').write_text(json.dumps(manifest))
    monkeypatch.setattr(installer, 'run', lambda *a, **kw: pytest.fail('No operation may run for an invalid release'))
    with pytest.raises(ValueError):
        installer.install(release, COMMIT, live)
    assert {p.name: p.read_bytes() for p in live.iterdir()} == before


def test_valid_release_retains_credentials_domains_and_takes_backup_first(release, live, monkeypatch):
    commands = []
    monkeypatch.setattr(installer, 'run', lambda *args, **kwargs: commands.append(args))
    installer.install(release, COMMIT, live)
    environment = dict(line.split('=', 1) for line in (live / '.env').read_text().splitlines())
    assert environment == {'APP_HOST': 'schedule.example.test', 'APP_HOST_ALIAS': 'azure.example.test',
                           'APP_IMAGE': 'smart-schedule:' + COMMIT,
                           'DJANGO_SECRET_KEY': 'private-existing-secret', 'POSTGRES_PASSWORD': 'private-existing-password'}
    assert stat.S_IMODE((live / '.env').stat().st_mode) == 0o600
    assert commands[0] == ('sh', str(live / 'backup.sh'))
    assert commands[1][:3] == ('docker', 'image', 'load')
    assert commands[-1] == ('sh', str(live / 'deploy.sh'))
    assert json.loads((live / 'last-deployment.json').read_text())['status'] == 'healthy'
    assert list((live / 'release-config-backups').glob('*/.env'))[0].read_text().find('APP_IMAGE=smart-schedule:previous') >= 0


def test_backup_failure_does_not_change_live_environment(release, live, monkeypatch):
    before = (live / '.env').read_bytes()
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(installer, 'run', fail)
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(release, COMMIT, live)
    assert (live / '.env').read_bytes() == before


def test_failed_deployment_closes_public_access_and_records_failure(release, live, monkeypatch):
    def run(*args, **kwargs):
        if args == ('sh', str(live / 'deploy.sh')):
            raise subprocess.CalledProcessError(1, args)
    commands = []
    monkeypatch.setattr(installer, 'run', run)
    monkeypatch.setattr(installer.subprocess, 'run', lambda args, **kwargs: commands.append(args))
    with pytest.raises(subprocess.CalledProcessError):
        installer.install(release, COMMIT, live)
    assert commands[-1][-3:] == ['stop', 'proxy', 'web']
    assert json.loads((live / 'last-deployment.json').read_text())['status'] == 'failed'
    assert not any('pg_restore' in str(command) for command in commands)


def test_an_in_progress_manual_deployment_prevents_install(release, live, monkeypatch):
    (live / '.deploy-lock').mkdir()
    monkeypatch.setattr(installer, 'run', lambda *a, **kw: pytest.fail('A deployment is already active'))
    with pytest.raises(ValueError, match='Another deployment'):
        installer.install(release, COMMIT, live)
