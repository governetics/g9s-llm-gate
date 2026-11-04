"""Shared helpers: load the template and parse the policy content it carries."""
import pathlib

import pytest
import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "deploy" / "compose.yml"


def load_template():
    return yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))


def policy_source():
    """The policy YAML exactly as the template ships it (raw text)."""
    return load_template()["configs"]["policy_yaml"]["content"]


@pytest.fixture(scope="session")
def template():
    return load_template()


@pytest.fixture(scope="session")
def policy():
    """The policy YAML parsed: routing settings as LiteLLM will read them."""
    return yaml.safe_load(policy_source())
