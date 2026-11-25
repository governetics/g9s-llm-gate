"""`docker compose config` over the template: rendering and fail-loud keys.

Needs a docker CLI with compose; skipped without it. This renders the model
only -- nothing is started.
"""
import json
import os
import shutil
import subprocess

import pytest

from conftest import TEMPLATE, load_template

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not found")

VALUES = {
    "LLM_GATE_BIND": "127.0.0.1",
    "LLM_GATE_PORT": "4000",
    "LLM_GATE_MASTER_KEY": "sk-test-only-master",
    "LLM_GATE_SALT_KEY": "test-only-salt",
    "LLM_GATE_POSTGRES_PASSWORD": "testonlypg123",
}


def required_keys():
    envs = load_template()["x-g9s-config"]["envs"]
    return [k for k, p in envs.items() if p.get("presence", "required") == "required"]


def compose(env_values, tmp_path, *args):
    """Render the model. Keys go through --env-file, the channel the
    platform's agent uses; the process environment carries no LLM_GATE_*
    or COMPOSE_* variables."""
    env_file = tmp_path / "keys.env"
    env_file.write_text("".join("%s=%s\n" % kv for kv in env_values.items()))
    env = {"PATH": os.environ["PATH"],
           "HOME": os.environ.get("HOME", "/tmp")}
    return subprocess.run(
        ["docker", "compose", "-p", "llmgate-test", "-f", str(TEMPLATE),
         "--env-file", str(env_file), "config", *args],
        capture_output=True, text=True, env=env, timeout=60,
    )


def test_values_cover_every_required_key():
    assert sorted(VALUES) == sorted(required_keys())


LOCAL_OVERRIDE = TEMPLATE.with_name("compose.local.yml")


def test_local_override_mounts_the_policy_file(tmp_path):
    """The panel delivers the policy file; the local contour bind-mounts the
    same reference text through a local-only override (bind mounts are refused
    by the panel, so the override never enters the template)."""
    env_file = tmp_path / "keys.env"
    env_file.write_text("".join("%s=%s\n" % kv for kv in VALUES.items()))
    env = {"PATH": os.environ["PATH"],
           "HOME": os.environ.get("HOME", "/tmp")}
    out = subprocess.run(
        ["docker", "compose", "-p", "llmgate-test", "-f", str(TEMPLATE),
         "-f", str(LOCAL_OVERRIDE), "--env-file", str(env_file), "config", "--format", "json"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    litellm = json.loads(out.stdout)["services"]["litellm"]
    mounts = {(v["source"], v["target"]) for v in litellm["volumes"]}
    assert (str(TEMPLATE.with_name("policy.yaml")),
            "/etc/g9s/files/proxy_server_config.yaml") in mounts


def test_services_render(tmp_path):
    out = compose(VALUES, tmp_path, "--services")
    assert out.returncode == 0, out.stderr
    assert sorted(out.stdout.split()) == ["db", "litellm"]


def test_rendered_model(tmp_path):
    out = compose(VALUES, tmp_path, "--format", "json")
    assert out.returncode == 0, out.stderr
    assert "${" not in out.stdout  # full values -> nothing left to substitute
    model = json.loads(out.stdout)
    services = model["services"]
    assert sorted(services) == ["db", "litellm"]
    litellm = services["litellm"]
    port = litellm["ports"][0]
    assert str(port["host_ip"]) == "127.0.0.1"
    assert str(port["published"]) == "4000"
    assert int(port["target"]) == 4000
    env = litellm["environment"]
    assert env["LITELLM_MASTER_KEY"] == "sk-test-only-master"
    assert env["LITELLM_SALT_KEY"] == "test-only-salt"
    assert env["STORE_MODEL_IN_DB"] == "True"
    assert env["DATABASE_URL"] == "postgresql://llmgate:testonlypg123@db:5432/llmgate"
    db = services["db"]
    assert "ports" not in db  # no host publication for the database
    assert db["environment"]["POSTGRES_PASSWORD"] == "testonlypg123"
    assert db["environment"]["POSTGRES_USER"] == "llmgate"
    assert db["environment"]["POSTGRES_DB"] == "llmgate"
    # The policy is not compose config anymore: it is a panel-delivered file
    # the command reads by its delivered path (pinned by the template tests).
    assert "configs" not in model
    assert litellm["command"][:2] == ["--config", "/etc/g9s/files/proxy_server_config.yaml"]


@pytest.mark.parametrize("key", required_keys())
def test_empty_required_key_fails_loud(tmp_path, key):
    values = dict(VALUES, **{key: ""})
    out = compose(values, tmp_path, "--quiet")
    assert out.returncode != 0
    assert "%s is not set" % key in out.stderr


@pytest.mark.parametrize("key", required_keys())
def test_missing_required_key_fails_loud(tmp_path, key):
    values = {k: v for k, v in VALUES.items() if k != key}
    out = compose(values, tmp_path, "--quiet")
    assert out.returncode != 0
    assert "%s is not set" % key in out.stderr
