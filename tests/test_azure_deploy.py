"""Exercise deployment safeguards locally; never call Azure or Docker."""

import json
import os
import shutil
import stat
import subprocess
import sys

import pytest

from scripts import azure_deploy as deploy


SUBSCRIPTION = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def state(tmp_path):
    return deploy.prepare(SUBSCRIPTION, "canadacentral", "smartsched", "schedule-test", tmp_path / "private")


def test_generated_credentials_are_private_and_preserved(tmp_path):
    directory = tmp_path / "private"
    state = deploy.prepare(SUBSCRIPTION, "canadacentral", "smartsched", "schedule-test", directory)
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE((directory / "state.json").stat().st_mode) == 0o600
    assert len(state["djangoSecretKey"]) >= 50
    assert state["postgresPassword"] != state["djangoSecretKey"]
    with pytest.raises(deploy.DeploymentError, match="already exists"):
        deploy.prepare(SUBSCRIPTION, "canadacentral", "smartsched", "schedule-test", directory)
    assert json.loads((directory / "state.json").read_text()) == state


def test_secure_parameters_are_removed_even_when_deployment_fails():
    with pytest.raises(RuntimeError):
        with deploy.parameter_file({"postgresPassword": "private-example"}) as path:
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
            assert json.loads(path.read_text())["parameters"]["postgresPassword"]["value"] == "private-example"
            raise RuntimeError("Interrupted deployment")
    assert not path.exists()


def test_no_billable_calls_without_approval(state, monkeypatch):
    monkeypatch.setattr(deploy, "az", lambda *a, **kw: pytest.fail("Azure must not be called"))
    with pytest.raises(deploy.DeploymentError, match="billable"):
        deploy.foundation(state)


def test_preview_uses_what_if_without_registering_or_creating_resources(state, monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(deploy, "STATE_DIR", tmp_path)
    monkeypatch.setattr(deploy, "save_state", lambda value: None)

    def azure(value, *args, **kwargs):
        commands.append(args)
        return {"status": "Succeeded", "changes": []}

    monkeypatch.setattr(deploy, "az", azure)
    deploy.foundation(state, preview=True)
    assert len(commands) == 1
    assert commands[0][:3] == ("deployment", "sub", "what-if")
    assert "--no-pretty-print" in commands[0]
    assert state["resources"] == {}
    assert json.loads((tmp_path / "preview.json").read_text())["status"] == "Succeeded"


def test_azure_cli_errors_are_reported_without_parameter_values(state, monkeypatch):
    def failed(command, **kwargs):
        assert state["postgresPassword"] not in command
        return subprocess.CompletedProcess(command, 1, "", "Quota or regional policy blocked this resource")

    monkeypatch.setattr(subprocess, "run", failed)
    with pytest.raises(deploy.DeploymentError, match="Quota or regional policy"):
        deploy.az(state, "deployment", "sub", "what-if")


@pytest.mark.parametrize("receipt", [None, {}, {"exitCode": 1, "imageReference": "registry/image@digest"}, {"exitCode": 0, "imageReference": "registry/old@digest"}])
def test_publish_rejects_missing_failed_or_stale_migration(state, receipt, monkeypatch):
    state.update(resources={"webName": "example"}, imageReference="registry/image@digest", migration=receipt)
    monkeypatch.setattr(deploy, "az", lambda *a, **kw: pytest.fail("Azure must not be called"))
    with pytest.raises(deploy.DeploymentError, match="verified migration"):
        deploy.deploy_web(state, publish=True)


def test_publish_rejects_configuration_changed_since_verification(state, monkeypatch):
    state.update(resources={"webName": "example"}, imageReference="registry/image@digest", migration={"exitCode": 0, "imageReference": "registry/image@digest"})
    monkeypatch.setattr(deploy, "az", lambda *a, **kw: {"linuxFxVersion": "DOCKER|registry/other@digest"})
    with pytest.raises(deploy.DeploymentError, match="image changed"):
        deploy.deploy_web(state, publish=True)


@pytest.mark.parametrize("result", [0, 7, None])
def test_only_observed_success_records_migration_receipt(state, result, monkeypatch):
    state.update(resources={"webName": "example"}, imageReference="registry/image@digest", published=False)
    monkeypatch.setattr(deploy, "save_state", lambda value: None)
    monkeypatch.setattr(deploy, "check_running_image", lambda value: None)
    monkeypatch.setattr(deploy, "az", lambda *a, **kw: [{"name": "instance-one"}])

    def remote(*args):
        if result is None:
            raise deploy.DeploymentError("Remote completion is unknown")
        return result

    monkeypatch.setattr(deploy, "remote_shell_result", remote)
    if result == 0:
        deploy.migrate(state)
        assert state["migration"]["exitCode"] == 0
        assert state["migration"]["imageReference"] == state["imageReference"]
    else:
        with pytest.raises(deploy.DeploymentError):
            deploy.migrate(state)
        assert state["migration"] is None
    assert state["published"] is False


@pytest.mark.parametrize("exit_code", [0, 9])
def test_shell_waits_for_raw_terminal_then_observes_real_exit(exit_code):
    # Like Azure CLI, the child switches to raw mode after establishing a
    # connection, flushing anything queued before that point.
    child = (
        "import os,subprocess,sys,time,tty; "
        "time.sleep(0.15); tty.setraw(0); "
        "command=sys.stdin.readline(); "
        "subprocess.run(command,shell=True,executable='/bin/sh')"
    )
    assert deploy.remote_shell_result([sys.executable, "-c", child], f"(exit {exit_code})", timeout=5) == exit_code


def test_echoed_command_without_execution_does_not_count_as_success():
    child = "import sys,tty; tty.setraw(0); print(sys.stdin.readline(), flush=True)"
    with pytest.raises(deploy.DeploymentError, match="completion is unknown"):
        deploy.remote_shell_result([sys.executable, "-c", child], "true", timeout=3)


@pytest.fixture(scope="module")
def compiled_templates(tmp_path_factory):
    binary = os.environ.get("BICEP_BIN") or shutil.which("bicep")
    if not binary:
        pytest.skip("Set BICEP_BIN to run compiled Azure infrastructure checks")
    directory = tmp_path_factory.mktemp("bicep")
    result = {}
    for name in ("main", "web"):
        output = directory / f"{name}.json"
        subprocess.run([binary, "build", str(deploy.ROOT / f"infra/azure/{name}.bicep"), "--outfile", str(output)], check=True, capture_output=True)
        result[name] = json.loads(output.read_text())
    return result


def test_compiled_foundation_keeps_database_private_and_registry_authenticated(compiled_templates):
    module = next(x for x in compiled_templates["main"]["resources"] if x["type"] == "Microsoft.Resources/deployments")
    template = module["properties"]["template"]
    resources = template["resources"]
    postgres = next(x for x in resources if x["type"] == "Microsoft.DBforPostgreSQL/flexibleServers")
    assert postgres["properties"]["network"]["publicNetworkAccess"] == "Disabled"
    assert postgres["properties"]["backup"]["backupRetentionDays"] == 7
    assert postgres["dependsOn"]
    assert not any(x["type"].endswith("/firewallRules") for x in resources)
    registry = next(x for x in resources if x["type"] == "Microsoft.ContainerRegistry/registries")
    assert registry["properties"]["adminUserEnabled"] is False
    assert registry["properties"]["anonymousPullEnabled"] is False
    assert template["parameters"]["postgresPassword"]["type"] == "securestring"


def test_compiled_web_requires_https_identity_verified_tls_and_explicit_publication(compiled_templates):
    template = compiled_templates["web"]
    resources = template["resources"]
    web = next(x for x in resources if x["type"] == "Microsoft.Web/sites")
    assert web["properties"]["httpsOnly"] is True
    assert web["identity"]["type"] == "UserAssigned"
    config = web["properties"]["siteConfig"]
    assert config["acrUseManagedIdentityCreds"] is True
    assert config["ftpsState"] == "Disabled"
    assert template["parameters"]["publishPublicly"]["defaultValue"] is False
    assert "publishPublicly" in config["ipSecurityRestrictionsDefaultAction"]
    settings = next(x for x in resources if x["type"] == "Microsoft.Web/sites/config")["properties"]
    assert settings["PGSSLMODE"] == "verify-full"
    assert "defaultHostName" in settings["DJANGO_ALLOWED_HOSTS"]
    assert template["parameters"]["djangoSecretKey"]["type"] == "securestring"
