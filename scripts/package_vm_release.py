"""Package the CI-tested image and an explicit list of deployment files."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


ROOT = Path(__file__).resolve().parents[1]
FILES = {
    'compose.yaml': 'compose.vm.yaml',
    'Caddyfile': 'docker/vm/Caddyfile',
    'deploy.sh': 'docker/vm/deploy.sh',
    'backup.sh': 'docker/vm/backup.sh',
    'install_release.py': 'docker/vm/install_release.py',
}


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def package(archive, commit, output, source=ROOT):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Use the complete Git commit SHA.')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(archive, output / 'app-image.tar')
    for name, relative in FILES.items():
        shutil.copyfile(source / relative, output / name)
    manifest = {'schema': 1, 'commit': commit, 'image': f'smart-schedule:{commit}',
                'files': {name: checksum(output / name) for name in ['app-image.tar', *FILES]}}
    (output / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package(args.archive, args.commit, args.output)
