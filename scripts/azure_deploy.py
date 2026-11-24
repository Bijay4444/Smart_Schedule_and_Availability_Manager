"""Staged Azure deployment: preview, approve costs, migrate, then publish.

Requires Azure CLI >= 2.90, Docker, and an authorized Azure sign-in. Secrets are
kept only in the ignored .azure-deploy directory and secure ARM parameters.
"""

import argparse
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import tempfile
import uuid


ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / ".azure-deploy"
STATE_PATH = STATE_DIR / "state.json"
PROVIDERS = ("Microsoft.Web", "Microsoft.Network", "Microsoft.DBforPostgreSQL", "Microsoft.ContainerRegistry", "Microsoft.ManagedIdentity")


class DeploymentError(Exception):
    pass


def save_state(state, directory=STATE_DIR):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    directory.chmod(0o700)
    target = directory / "state.json"
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
        json.dump(state, output, indent=2)
        temporary = Path(output.name)
    temporary.replace(target)


def prepare(subscription, location, prefix, group, directory=STATE_DIR):
    uuid.UUID(subscription)
    if not re.fullmatch(r"[a-z][a-z0-9]{2,11}", prefix):
        raise DeploymentError("Prefix must be 3–12 lowercase letters/digits, beginning with a letter.")
    if not re.fullmatch(r"[a-z0-9]+", location):
        raise DeploymentError("Use an Azure region code such as canadacentral.")
    if (directory / "state.json").exists():
        raise DeploymentError("Deployment state already exists; keep it to preserve database credentials.")
    state = {
        "subscription": str(uuid.UUID(subscription)), "location": location,
        "prefix": prefix, "resourceGroup": group,
        "postgresPassword": "Aa1!" + secrets.token_urlsafe(36),
        "djangoSecretKey": secrets.token_urlsafe(50),
        "resources": {}, "imageReference": None, "migration": None,
    }
    save_state(state, directory)
    return state


def load_state():
    if not STATE_PATH.exists():
        raise DeploymentError("Run prepare first with the explicit student subscription ID.")
    return json.loads(STATE_PATH.read_text())


def az(state, *args, capture=True):
    command = shlex.split(os.environ.get("AZURE_CLI_COMMAND", "az"))
    command += [*args, "--subscription", state["subscription"], "--only-show-errors"]
    if capture:
        command += ["--output", "json"]
    result = subprocess.run(command, check=False, text=True, capture_output=capture)
    if result.returncode:
        # CLI error output explains quota/policy failures; values from the
        # private parameter file are never included in our command line.
        raise DeploymentError(result.stderr.strip() if capture else "Azure CLI command failed; see output above.")
    return json.loads(result.stdout) if capture and result.stdout.strip() else None


@contextmanager
def parameter_file(parameters):
    # Sensitive values stay out of process arguments and terminal output.
    with tempfile.TemporaryDirectory(prefix="smart-azure-parameters-") as directory:
        path = Path(directory) / "parameters.json"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as output:
            json.dump({"parameters": {name: {"value": value} for name, value in parameters.items()}}, output)
        yield path


def foundation_parameters(state):
    return {name: state[name] for name in ("location", "prefix", "postgresPassword")} | {"resourceGroupName": state["resourceGroup"]}


def foundation(state, approve=False, preview=False):
    if not preview and not approve:
        raise DeploymentError("Provisioning is billable. Review docs/azure_deployment.md and pass --approve-costs only after approving the setup.")
    if not preview:
        for provider in PROVIDERS:
            az(state, "provider", "register", "--namespace", provider, "--wait", capture=False)
    with parameter_file(foundation_parameters(state)) as path:
        command = "what-if" if preview else "create"
        options = ["--no-pretty-print"] if preview else []
        result = az(state, "deployment", "sub", command, *options, "--name", "smart-schedule-foundation",
                    "--location", state["location"], "--template-file", str(ROOT / "infra/azure/main.bicep"),
                    "--parameters", f"@{path}")
    if preview:
        # ARM hides secure parameter values in its change preview.
        save_state(state)
        (STATE_DIR / "preview.json").write_text(json.dumps(result, indent=2))
        print("Preview saved to .azure-deploy/preview.json; no resources were created.")
    else:
        state["resources"] = result["properties"]["outputs"]["resources"]["value"]
        save_state(state)
        print("Foundation provisioned. Next: build, deploy-web, migrate, publish.")


def build(state):
    resources = state["resources"]
    if not resources:
        raise DeploymentError("Provision the approved foundation before pushing an image.")
    registry = resources["registryName"]
    server = resources["registryServer"]
    tag = datetime.now(UTC).strftime("release-%Y%m%dT%H%M%S-") + secrets.token_hex(3)
    repository_tag = f"smart-schedule:{tag}"
    local_tag = f"{server}/{repository_tag}"
    az(state, "acr", "login", "--name", registry, capture=False)
    subprocess.run(["docker", "build", "--platform", "linux/amd64", "--target", "runtime", "-t", local_tag, str(ROOT)], check=True)
    subprocess.run(["docker", "push", local_tag], check=True)
    metadata = az(state, "acr", "repository", "show", "--name", registry, "--image", repository_tag)
    digest = metadata["digest"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise DeploymentError("Registry did not return a valid immutable image digest.")
    state["imageReference"] = f"{server}/smart-schedule@{digest}"
    state["migration"] = None
    save_state(state)
    print("Image pushed and pinned by digest. Next: deploy-web.")


def ensure_publishable(state):
    receipt = state.get("migration") or {}
    if not state.get("imageReference") or receipt.get("imageReference") != state["imageReference"] or receipt.get("exitCode") != 0:
        raise DeploymentError("Publication requires a verified migration/check result for this exact image.")


def check_running_image(state):
    actual = az(state, "webapp", "config", "show", "--resource-group", state["resourceGroup"], "--name", state["resources"]["webName"])
    if actual.get("linuxFxVersion") != "DOCKER|" + state["imageReference"]:
        raise DeploymentError("The configured app image changed; deploy and verify the intended image first.")


def deploy_web(state, publish=False):
    if not state.get("imageReference") or not state["resources"]:
        raise DeploymentError("Provision and build before deploying the web app.")
    if publish:
        ensure_publishable(state)
        check_running_image(state)
    parameters = {name: state[name] for name in ("prefix", "location", "postgresPassword", "djangoSecretKey", "imageReference")}
    parameters["publishPublicly"] = publish
    with parameter_file(parameters) as path:
        result = az(state, "deployment", "group", "create", "--name", "smart-schedule-web",
                    "--resource-group", state["resourceGroup"], "--template-file", str(ROOT / "infra/azure/web.bicep"),
                    "--parameters", f"@{path}")
    if not publish:
        state["migration"] = None
    state["url"] = result["properties"]["outputs"]["url"]["value"]
    state["published"] = publish
    save_state(state)
    print(state["url"] if publish else "Web container deployed with public application access denied. Next: migrate.")


def remote_shell_result(command, shell_command, timeout=600):
    """Observe a real shell result; never mistake detached 'accepted' for success.

    An interrupted/unknown result is an error, and is never retried automatically.
    The marker uses a printf placeholder, so terminal echo cannot fake its value.
    """
    import errno
    import pty
    import select
    import termios
    import time

    marker = "SCHEDULE_RESULT_" + secrets.token_hex(12)
    payload = f"{shell_command}; result=$?; printf '\\n{marker}:%s\\n' \"$result\"; exit \"$result\"\n"
    master, slave = pty.openpty()
    process = subprocess.Popen(command, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
    os.close(slave)
    output = b""
    deadline = time.monotonic() + timeout
    sent = False
    try:
        while time.monotonic() < deadline:
            # Azure CLI calls tty.setraw(TCSAFLUSH) after connecting. Sending
            # earlier would silently discard queued input. Wait for raw mode.
            if not sent and not termios.tcgetattr(master)[3] & (termios.ICANON | termios.ECHO):
                os.write(master, payload.encode())
                sent = True
            if not select.select([master], [], [], 0.1)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError as error:
                if error.errno == errno.EIO:
                    break
                raise
            if not chunk:
                break
            output = (output + chunk)[-131072:]
            print(chunk.decode(errors="replace"), end="", flush=True)
            match = re.search(rb"(?:\r?\n)" + marker.encode() + rb":(\d+)\r?\n", output)
            if match:
                return int(match[1])
        raise DeploymentError("Remote completion is unknown. Public access stays closed. Inspect the one selected instance; do not blindly rerun a migration.")
    finally:
        os.close(master)
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=15)


def migrate(state):
    if not state.get("imageReference") or state.get("published") is not False:
        raise DeploymentError("Deploy the image with public access denied before running migrations.")
    name = state["resources"]["webName"]
    check_running_image(state)
    instances = az(state, "webapp", "list-instances", "--resource-group", state["resourceGroup"], "--name", name)
    if len(instances) != 1:
        raise DeploymentError("Expected exactly one app instance; select and supervise a single instance manually.")
    instance = instances[0].get("name") or instances[0]["id"].rsplit("/", 1)[-1]
    command = shlex.split(os.environ.get("AZURE_CLI_COMMAND", "az")) + [
        "webapp", "exec", "--subscription", state["subscription"], "--resource-group", state["resourceGroup"],
        "--name", name, "--instance", instance, "--mode", "shell", "--shell", "/bin/sh",
    ]
    # Clear any old proof before beginning an operation that may be interrupted.
    state["migration"] = None
    save_state(state)
    code = remote_shell_result(command, "cd /app && /app/.venv/bin/python manage.py migrate --noinput && /app/.venv/bin/python manage.py check --deploy")
    if code != 0:
        raise DeploymentError(f"Migration/check failed with exit status {code}; public access stays closed.")
    check_running_image(state)
    state["migration"] = {"exitCode": code, "imageReference": state["imageReference"], "instance": instance, "verifiedAt": datetime.now(UTC).isoformat()}
    save_state(state)
    print("Migration and deployment checks completed successfully. Next: publish.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "plan", "provision", "build", "deploy-web", "migrate", "publish", "status"])
    parser.add_argument("--subscription")
    parser.add_argument("--location", default="northcentralus")
    parser.add_argument("--prefix", default="smartsched")
    parser.add_argument("--resource-group", default="smart-schedule-prod")
    parser.add_argument("--approve-costs", action="store_true")
    args = parser.parse_args()
    try:
        if args.stage == "prepare":
            if not args.subscription:
                raise DeploymentError("Pass the explicit Azure for Students subscription ID.")
            prepare(args.subscription, args.location, args.prefix, args.resource_group)
            print("Private deployment state created. No cloud resources were created. Next: plan.")
            return
        state = load_state()
        if args.stage == "plan": foundation(state, preview=True)
        elif args.stage == "provision": foundation(state, approve=args.approve_costs)
        elif args.stage == "build": build(state)
        elif args.stage == "deploy-web": deploy_web(state)
        elif args.stage == "migrate": migrate(state)
        elif args.stage == "publish": deploy_web(state, publish=True)
        else:
            print(json.dumps({name: state.get(name) for name in ("subscription", "resourceGroup", "location", "url", "imageReference", "published")}, indent=2))
    except (DeploymentError, ValueError, subprocess.CalledProcessError, FileNotFoundError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
