"""Text pins of the deploy template.

These tests clamp the TEXT of deploy/compose.yml by walking the parsed YAML;
they are not behavioural. Behaviour is checked by `docker compose config`
(test_compose_config.py), the platform parser (test_platform_parser.py) and
the phase 1+ live probes.
"""
import hashlib
import re
import subprocess

import yaml

from conftest import ROOT, TEMPLATE, policy_source

SUBST = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(:\?|:-|\?|-)?")

# Keys the governetics panel must hide in its UI and logs: their values are
# live secrets (master key, salt, database password).
INVISIBLE_KEYS = {
    "LLM_GATE_MASTER_KEY",
    "LLM_GATE_SALT_KEY",
    "LLM_GATE_POSTGRES_PASSWORD",
}


def body_text():
    """Template text without the x-g9s-config header block."""
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("x-g9s-config:")
    end = text.index("\nconfigs:", start)
    return text[:start] + text[end:]


def env_keys(template):
    return template["x-g9s-config"]["envs"]


def test_every_service_has_healthcheck_restart_and_log_rotation(template):
    for name, svc in template["services"].items():
        hc = svc.get("healthcheck") or {}
        assert hc.get("test") and not hc.get("disable"), name
        assert hc["test"][0] in ("CMD", "CMD-SHELL"), name
        assert svc.get("restart") == "unless-stopped", name
        logging = svc.get("logging") or {}
        assert logging.get("driver") == "json-file", name
        assert logging.get("options", {}).get("max-size"), name


def test_no_depends_on_service_healthy(template):
    for name, svc in template["services"].items():
        deps = svc.get("depends_on")
        if isinstance(deps, dict):
            for dep, spec in deps.items():
                assert (spec or {}).get("condition") != "service_healthy", (name, dep)
        # list form carries no condition; any other form is refused
        assert deps is None or isinstance(deps, (list, dict)), name


def test_no_external_or_shared_networks(template):
    for net in (template.get("networks") or {}).values():
        assert not (net or {}).get("external"), net
    for name, svc in template["services"].items():
        assert "network_mode" not in svc, name
        assert "networks" not in svc, name
    assert "networks" not in template


def test_volumes_long_syntax_only(template):
    for name, svc in template["services"].items():
        for vol in svc.get("volumes", []):
            assert isinstance(vol, dict), (name, vol)  # short syntax refused
            assert vol["type"] == "volume", (name, vol)  # no bind mounts


def test_db_has_no_host_ports(template):
    assert "ports" not in template["services"]["db"]


def uncommented_body_text():
    """Body text with comment lines stripped: pins about substitutions must
    read the code, not the ${KEY:?...} example in the header comment."""
    return re.sub(r"(^|\s)#.*$", "", body_text(), flags=re.MULTILINE)


def test_every_declared_key_has_consumer_and_is_used(template):
    services = set(template["services"])
    used = {m.group(1) for m in SUBST.finditer(uncommented_body_text())}
    for key, props in env_keys(template).items():
        consumers = props.get("consumers") or []
        assert consumers and set(consumers) <= services, key
    # Completeness both ways: every declared key is substituted in the body,
    # every substitution stands for a declared key.
    assert used == set(env_keys(template))


def test_required_keys_only_in_fail_loud_form(template):
    body = body_text()
    for key, props in env_keys(template).items():
        required = props.get("presence", "required") == "required"
        forms = [m.group(2) for m in SUBST.finditer(body) if m.group(1) == key]
        assert required, key  # no optional keys yet; keep the general shape
        if required:
            assert forms, key
            assert all(f == ":?" for f in forms), (key, forms)


def test_secret_keys_are_invisible(template):
    for key in INVISIBLE_KEYS:
        assert key in env_keys(template), key
        assert env_keys(template)[key].get("visibility") == "invisible", key


def test_secret_env_values_are_substitutions_only(template):
    """No secret literal in the body: every secret-bearing env value is a
    ${KEY:?...} substitution, never inline text."""
    litellm_env = template["services"]["litellm"]["environment"]
    for var in ("LITELLM_MASTER_KEY", "LITELLM_SALT_KEY"):
        assert isinstance(litellm_env[var], str), var
        assert litellm_env[var].startswith("${"), var
    # DATABASE_URL embeds the password substitution inside a DSN template:
    # the password must arrive only through the fail-loud form.
    password_subst = (
        "${LLM_GATE_POSTGRES_PASSWORD:?LLM_GATE_POSTGRES_PASSWORD is not set}")
    assert litellm_env["DATABASE_URL"].startswith("postgresql://llmgate:")
    assert password_subst in litellm_env["DATABASE_URL"]
    assert litellm_env["DATABASE_URL"].endswith("@db:5432/llmgate")
    db_env = template["services"]["db"]["environment"]
    assert db_env["POSTGRES_PASSWORD"] == password_subst


def test_image_pins(template):
    litellm = template["services"]["litellm"]["image"]
    db = template["services"]["db"]["image"]
    assert litellm == "ghcr.io/berriai/litellm:v1.108.0"  # pinned, not latest
    assert re.fullmatch(r"postgres:16\.\d+", db), db  # minor pin, not 16/latest


def test_litellm_command_pins_config(template):
    svc = template["services"]["litellm"]
    # The image starts with an empty model list without an explicit --config.
    assert svc["command"] == ["--config", "/app/proxy_server_config.yaml",
                              "--port", "4000"]
    assert svc["configs"] == [
        {"source": "policy_yaml", "target": "/app/proxy_server_config.yaml",
         "mode": 0o444},
    ]


def test_litellm_publication_pin(template):
    svc = template["services"]["litellm"]
    assert svc["ports"] == [
        "${LLM_GATE_BIND:?LLM_GATE_BIND is not set}"
        ":${LLM_GATE_PORT:?LLM_GATE_PORT is not set}:4000",
    ]


def test_litellm_environment_contract(template):
    env = template["services"]["litellm"]["environment"]
    assert env["STORE_MODEL_IN_DB"] == "True"
    assert env["DATABASE_URL"] == (
        "postgresql://llmgate:"
        "${LLM_GATE_POSTGRES_PASSWORD:?LLM_GATE_POSTGRES_PASSWORD is not set}"
        "@db:5432/llmgate")
    db_env = template["services"]["db"]["environment"]
    assert db_env["POSTGRES_USER"] == "llmgate"
    assert db_env["POSTGRES_DB"] == "llmgate"


def test_litellm_healthcheck_liveliness_not_health(template):
    cmd = template["services"]["litellm"]["healthcheck"]["test"]
    assert cmd[:2] == ["CMD", "python3"]
    probe = cmd[-1]
    assert "urllib" in probe  # a tool present in the image, no curl needed
    assert "'http://127.0.0.1:4000/health/liveliness'" in probe
    # /health spends real upstream tokens: it must not appear as a probe URL.
    assert not re.search(r"['\"]http[^'\"]*/health['\"]", probe)


def test_db_healthcheck_pg_isready(template):
    cmd = template["services"]["db"]["healthcheck"]["test"]
    assert cmd[0] == "CMD"
    assert cmd[1] == "pg_isready"
    assert "-U" in cmd and "-d" in cmd


def test_configs_are_content_only(template):
    for cname, cfg in template.get("configs", {}).items():
        assert set(cfg) == {"content"}, cname  # no file: / environment: sources
    assert "secrets" not in template
    for name, svc in template["services"].items():
        for field in ("env_file", "secrets", "build", "extends", "devices"):
            assert field not in svc, (name, field)


def test_policy_hash_label_tracks_content(template):
    """A policy change must recreate the container: compose ignores config
    content changes on its own."""
    content = template["configs"]["policy_yaml"]["content"]
    label = template["services"]["litellm"]["labels"]["llmgate.policy-sha256"]
    assert label == hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def test_policy_content_has_no_dollar(template):
    # compose interpolates config content; the panel stubs ${...} before
    # parsing the template
    assert "$" not in template["configs"]["policy_yaml"]["content"]


def test_only_braced_substitutions_in_body():
    """Every "$" in the body is a ${KEY...} substitution: no bare $KEY (which
    would dodge the fail-loud form pin) and no $$ escapes."""
    no_comments = re.sub(r"(^|\s)#.*$", "", body_text(), flags=re.MULTILINE)
    rest = re.sub(r"\$\{[A-Za-z_][A-Za-z0-9_]*(:\?|:-)[^}]*\}", "", no_comments)
    assert "$" not in rest


def test_policy_contract(template, policy):
    """Routing policy and nothing else: cross fallbacks by public alias,
    two retries, no model definitions, no provider names."""
    fallbacks = {}
    for entry in policy["router_settings"]["fallbacks"]:
        assert isinstance(entry, dict) and len(entry) == 1, entry
        fallbacks.update(entry)
    assert fallbacks == {"top": ["optimal"], "optimal": ["top"],
                         "fast": ["cheap"], "cheap": ["fast"]}
    assert policy["litellm_settings"]["num_retries"] == 2
    assert set(policy) == {"router_settings", "litellm_settings"}


def test_a3_no_secrets_in_template_or_policy(template):
    """A3 pin-on-absence: secrets stay out of VCS and out of the template.

    Targets the invariant, not the wording: whichever way the template is
    rewritten, these must not reappear -- provider names (models/credentials
    are DB/UI-owned), live key material, model definitions or credential
    fields inside the policy.
    """
    text = TEMPLATE.read_text(encoding="utf-8").lower()
    # Provider names have no reason to exist in the artifact: models and
    # credentials are owned by the database / Admin UI.
    assert "kimi" not in text
    assert "glm" not in text
    # Live key material: the only allowed "sk-" is the prefix mention in a
    # comment, never key-shaped data (8+ chars after the dash).
    assert not re.search(r"sk-[a-z0-9_-]{8,}", text)
    # The policy carries routing only: no model list, no per-model params,
    # no credential fields.
    policy_text = policy_source().lower()
    for banned in ("model_list", "litellm_params", "api_key", "api_base"):
        assert banned not in policy_text, banned
    parsed = yaml.safe_load(policy_source())
    assert set(parsed) == {"router_settings", "litellm_settings"}


def test_gitignore_pins_secret_paths():
    """The VCS half of A3, as a behavioural probe: git itself must keep
    swallowing secret paths. A dropped .env line turns this red instead of
    letting the next local .env leak into a commit."""
    ignored = (".env", "secrets/providers/kimi-coding.key", "x.key", "x.pem")
    for path in ignored:
        r = subprocess.run(["git", "check-ignore", "--", path], cwd=ROOT,
                           capture_output=True, text=True)
        assert r.returncode == 0, path  # ignored
    # The example env is meant for VCS: the negation must keep working.
    r = subprocess.run(["git", "check-ignore", "--", ".env.example"], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 1, ".env.example must stay un-ignored"
