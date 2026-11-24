"""Create local Compose secrets once; reruns must preserve database credentials."""

import os
from pathlib import Path
import secrets


def create_environment(project_root):
    target = project_root / ".env.docker"
    if target.exists():
        return False
    content = (project_root / ".env.docker.example").read_text()
    content = content.replace("DJANGO_SECRET_KEY=\n", f"DJANGO_SECRET_KEY={secrets.token_urlsafe(50)}\n")
    content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}\n")
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w") as output:
        output.write(content)
    return True


if __name__ == "__main__":
    created = create_environment(Path(__file__).resolve().parents[1])
    print("Created .env.docker with private local secrets." if created else "Kept existing .env.docker unchanged.")
