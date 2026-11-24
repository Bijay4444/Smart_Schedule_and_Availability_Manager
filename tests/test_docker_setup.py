from pathlib import Path
import stat

from scripts.setup_docker_env import create_environment


def test_local_docker_setup_creates_private_secrets_without_touching_native_environment(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / ".env.docker.example").write_text((root / ".env.docker.example").read_text())
    (tmp_path / ".env").write_text("native-environment-must-stay\n")
    assert create_environment(tmp_path)
    target = tmp_path / ".env.docker"
    values = dict(line.split("=", 1) for line in target.read_text().splitlines() if line and not line.startswith("#"))
    assert len(values["DJANGO_SECRET_KEY"]) >= 50
    assert len(values["POSTGRES_PASSWORD"]) >= 32
    assert values["DJANGO_SECRET_KEY"] != values["POSTGRES_PASSWORD"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert (tmp_path / ".env").read_text() == "native-environment-must-stay\n"


def test_local_docker_setup_never_rotates_existing_credentials(tmp_path):
    target = tmp_path / ".env.docker"
    target.write_text("manually-configured-credentials\n")
    assert not create_environment(tmp_path)
    assert target.read_text() == "manually-configured-credentials\n"
