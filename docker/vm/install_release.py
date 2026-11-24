"""Install a verified CI bundle while retaining the VM's private environment.

Run with sudo: python3 install_release.py <incoming-directory> <commit>.
Only trusted main-branch jobs may invoke this privileged deployment command.
"""

import argparse
from datetime import UTC, datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


DEPLOYMENT_FILES = ('compose.yaml', 'Caddyfile', 'deploy.sh', 'backup.sh')
EXPECTED_FILES = {'app-image.tar', 'install_release.py', *DEPLOYMENT_FILES}


def validate(release, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid commit SHA')
    manifest = json.loads((release / 'release.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('commit') != commit or manifest.get('image') != f'smart-schedule:{commit}':
        raise ValueError('Release metadata does not match the requested commit')
    if set(manifest.get('files', {})) != EXPECTED_FILES or (release / '.env').exists():
        raise ValueError('Release files do not match the allowlist')
    for name, expected in manifest['files'].items():
        path = release / name
        if path.is_symlink() or not path.is_file():
            raise ValueError('Release contains an invalid file')
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise ValueError(f'Checksum failed: {name}')
    return manifest


def atomic_write(path, content):
    previous = path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        if previous:
            os.fchown(stream.fileno(), previous.st_uid, previous.st_gid)
        stream.write(content)
    temporary.replace(path)


def run(*args, cwd):
    subprocess.run(args, cwd=cwd, check=True)


def install(release, commit, target=Path('/opt/smart-schedule')):
    release, target = release.resolve(), target.resolve()
    manifest = validate(release, commit)
    environment = target / '.env'
    if not environment.is_file():
        raise ValueError('VM private .env is missing; never generate replacement credentials here')
    with (target / '.ci-deploy.lock').open('a') as lock:
        os.fchmod(lock.fileno(), 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (target / '.deploy-lock').exists():
            raise ValueError('Another deployment may be running; inspect it before retrying')
        old = environment.read_text()
        lines = old.splitlines()
        if sum(line.startswith('APP_IMAGE=') for line in lines) != 1:
            raise ValueError('Expected one APP_IMAGE entry in the private environment')
        # All validation, backup and image loading happen before public downtime.
        run('sh', str(target / 'backup.sh'), cwd=target)
        run('docker', 'image', 'load', '--input', str(release / 'app-image.tar'), cwd=target)
        run('docker', 'image', 'inspect', manifest['image'], '--format', '{{.Id}}', cwd=target)
        rollback = target / 'release-config-backups' / (commit + '-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S'))
        rollback.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name in ('.env', *DEPLOYMENT_FILES):
            shutil.copyfile(target / name, rollback / name)
            (rollback / name).chmod(0o600)
        for name in DEPLOYMENT_FILES:
            shutil.copyfile(release / name, target / name)
        updated = '\n'.join('APP_IMAGE=' + manifest['image'] if line.startswith('APP_IMAGE=') else line for line in lines) + '\n'
        atomic_write(environment, updated)
        state = {'commit': commit, 'image': manifest['image'], 'startedAt': datetime.now(UTC).isoformat(), 'status': 'deploying'}
        status = target / 'last-deployment.json'
        atomic_write(status, json.dumps(state, indent=2))
        try:
            run('sh', str(target / 'deploy.sh'), cwd=target)
        except subprocess.CalledProcessError:
            # Never roll back schemas automatically or expose an unverified app.
            subprocess.run(['docker', 'compose', '--env-file', '.env', '-f', 'compose.yaml', 'stop', 'proxy', 'web'], cwd=target, check=False)
            state['status'] = 'failed'
            atomic_write(status, json.dumps(state, indent=2))
            raise
        state.update(status='healthy', completedAt=datetime.now(UTC).isoformat())
        atomic_write(status, json.dumps(state, indent=2))
        history_path = target / 'ci-release-history.json'
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        history = [entry for entry in history if entry['path'] != str(release)]
        history.append({'path': str(release), 'image': manifest['image']})
        for entry in history[:-3]:
            previous = Path(entry['path']).resolve()
            if previous.parent == target / 'releases' and re.fullmatch(r'[0-9a-f]{40}-[0-9]+-[0-9]+', previous.name):
                shutil.rmtree(previous, ignore_errors=True)
            if re.fullmatch(r'smart-schedule:[0-9a-f]{40}', entry['image']) and entry['image'] not in {item['image'] for item in history[-3:]}:
                # No --force: Docker refuses to delete an image still in use.
                subprocess.run(['docker', 'image', 'rm', entry['image']], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        atomic_write(history_path, json.dumps(history[-3:], indent=2))
        print(f'Deployed commit {commit}; VM credentials and domains retained.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('commit')
    args = parser.parse_args()
    install(args.release, args.commit)
