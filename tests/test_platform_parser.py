"""The template header as the governetics panel parses it.

Runs the platform's own parser (panel.template_registry) from a governetics
checkout without writing to it. Skipped unless GOVERNETICS_ROOT points at a
checkout with a virtualenv in .venv/:

    GOVERNETICS_ROOT=/path/to/governetics python3 -m pytest tests
"""
import json
import os
import pathlib
import subprocess
import textwrap

import pytest

from conftest import TEMPLATE, load_template

ROOT = os.environ.get("GOVERNETICS_ROOT")
PYTHON = pathlib.Path(ROOT or "/nonexistent") / ".venv" / "bin" / "python"

pytestmark = pytest.mark.skipif(not PYTHON.exists(), reason="GOVERNETICS_ROOT with .venv not set")

PROBE = textwrap.dedent(
    """
    import json, sys
    sys.dont_write_bytecode = True
    sys.path.insert(0, sys.argv[1] + "/src")
    from panel import template_registry as tr
    text = open(sys.argv[2], encoding="utf-8").read()
    meta = tr.parse_template_headers(text)
    out = {
        "services": list(meta.services),
        "slots": meta.image_slots,
        "keys": {g: {k: {"consumers": list(d.consumers), "presence": d.presence,
                         "visibility": d.visibility} for k, d in keys.items()}
                 for g, keys in meta.config.items()},
        "env_precedence": tr.validate_compose_template_env_precedence(text),
        "bind_mounts": tr.validate_compose_template_bind_mounts(text),
    }
    print(json.dumps(out, default=str))
    """
)


def test_platform_accepts_header_and_gates():
    run = subprocess.run(
        [str(PYTHON), "-c", PROBE, ROOT, str(TEMPLATE)],
        capture_output=True, text=True, timeout=120,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )
    assert run.returncode == 0, run.stderr
    parsed = json.loads(run.stdout.strip().splitlines()[-1])
    # The parser lists services in declaration order; only membership matters.
    assert sorted(parsed["services"]) == ["db", "litellm"]
    assert parsed["env_precedence"] == [] and parsed["bind_mounts"] == []
    declared = load_template()["x-g9s-config"]
    assert sorted(parsed["keys"]["envs"]) == sorted(declared["envs"])
    for key, props in declared["envs"].items():
        assert key in parsed["keys"]["envs"], key
        assert sorted(parsed["keys"]["envs"][key]["consumers"]) == sorted(
            props["consumers"]), key
        assert parsed["keys"]["envs"][key]["presence"] == props.get(
            "presence", "required"), key
    assert parsed["keys"]["envs"]["LLM_GATE_MASTER_KEY"]["visibility"] == "invisible"
    assert parsed["keys"]["envs"]["LLM_GATE_SALT_KEY"]["visibility"] == "invisible"
    assert parsed["keys"]["envs"]["LLM_GATE_POSTGRES_PASSWORD"]["visibility"] == "invisible"
    assert sorted(parsed["keys"]["envs"]["LLM_GATE_POSTGRES_PASSWORD"]["consumers"]) == [
        "db", "litellm"]
