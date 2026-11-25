"""Shared helpers: load the template and the policy file it declares."""
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "compose.yml"
POLICY = ROOT / "deploy" / "policy.yaml"


def load_template():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def policy_source():
    """The policy YAML exactly as the operator pastes it into the panel
    (the reference text of the delivered `proxy_server_config.yaml`)."""
    return POLICY.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def template():
    return load_template()


@pytest.fixture(scope="session")
def policy():
    """The policy YAML parsed: routing settings as LiteLLM will read them."""
    return yaml.safe_load(policy_source())
