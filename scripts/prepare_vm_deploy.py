"""Create a private single-VM deployment bundle; never provision cloud resources."""

import argparse
import ipaddress
import os
from pathlib import Path
import re
import secrets
import shutil


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIRECTORY = ROOT / '.azure-deploy/vm/bundle'


def prepare_bundle(directory, hostname, image):
    # These values enter Compose and Caddy config. Accept DNS names and local
    # image tags, not URLs, shell syntax, wildcard hosts or Caddy directives.
    hostname = hostname.lower()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError('Use the actual DNS hostname, not an IP address.')
    label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    if len(hostname) > 253 or not re.fullmatch(rf'{label}(?:\.{label})+', hostname):
        raise ValueError('Use the actual DNS hostname without a scheme, port, or path.')
    if not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*:[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}', image):
        raise ValueError('Use an explicit local image tag, such as smart-schedule:vm-release-1.')
    directory = Path(directory)
    if (directory / '.env').exists():
        raise ValueError('A private environment already exists. Preserve its database credentials; update APP_IMAGE explicitly for later releases.')
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    values = {
        'APP_HOST': hostname,
        'APP_IMAGE': image,
        'DJANGO_SECRET_KEY': secrets.token_urlsafe(50),
        'POSTGRES_PASSWORD': secrets.token_urlsafe(36),
    }
    # Exclusive creation prevents a rerun from rotating credentials underneath
    # an existing PostgreSQL volume. The source development .env is never read.
    descriptor = os.open(directory / '.env', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(''.join(f'{key}={value}\n' for key, value in values.items()))
    shutil.copyfile(ROOT / 'compose.vm.yaml', directory / 'compose.yaml')
    for name in ('Caddyfile', 'deploy.sh', 'backup.sh'):
        shutil.copyfile(ROOT / 'docker/vm' / name, directory / name)
    for name in ('deploy.sh', 'backup.sh'):
        (directory / name).chmod(0o700)
    return directory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hostname', required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--directory', type=Path, default=DEFAULT_DIRECTORY)
    args = parser.parse_args()
    try:
        directory = prepare_bundle(args.directory, args.hostname, args.image)
    except (ValueError, OSError) as error:
        parser.exit(1, f'{error}\n')
    print(f'Private deployment bundle prepared at {directory}. No Azure resources were created.')


if __name__ == '__main__':
    main()
