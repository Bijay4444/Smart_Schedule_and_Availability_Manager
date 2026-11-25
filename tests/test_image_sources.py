"""Exercise the Dockerfile's actual source-copy set without requiring Docker locally."""
from pathlib import Path
import re
import shutil
import subprocess
import sys

from django.apps import apps

ROOT = Path(__file__).resolve().parents[1]


def test_image_source_tree_can_boot_django_and_collect_static(tmp_path):
    for source, destination in re.findall(r'^COPY (\S+) (\S+)$', (ROOT / 'Dockerfile').read_text(), re.M):
        target = tmp_path / destination.removeprefix('./')
        origin = ROOT / source
        if origin.is_dir():
            shutil.copytree(origin, target, ignore=shutil.ignore_patterns('__pycache__'))
        else:
            if destination.endswith('/'):
                target = target / origin.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin, target)
    result = subprocess.run([sys.executable, 'manage.py', 'collectstatic', '--noinput'], cwd=tmp_path,
        env={'DJANGO_SETTINGS_MODULE': 'config.django.base', 'DJANGO_SECRET_KEY': 'isolated-static-build-fixture'},
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / 'staticfiles/staticfiles.json').is_file()


def test_every_local_app_is_allowed_into_docker_context():
    lines = (ROOT / '.dockerignore').read_text().splitlines()
    for app in apps.get_app_configs():
        path = Path(app.path)
        if path.parent == ROOT:
            assert f'!{path.name}/' in lines and f'!{path.name}/**' in lines, app.name
