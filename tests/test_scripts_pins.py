"""Pins of the operator scripts (phase 2 review, K-2).

The syntax pin is behavioural (bash parses the script); the rest are TEXT
pins, called text pins on purpose: they clamp the load-bearing lines of
scripts/smoke.sh, backup.sh and restore.sh that no runtime test exercises
in CI. Behaviour of the scripts is validated live (smoke against a real
stack, backup/restore round trip) during phase acceptance.
"""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def script(name):
    return (SCRIPTS / name).read_text(encoding="utf-8")


def test_scripts_parse():  # behavioural: bash itself must accept each script
    for name in ("smoke.sh", "backup.sh", "restore.sh"):
        r = subprocess.run(["bash", "-n", str(SCRIPTS / name)],
                           capture_output=True, text=True)
        assert r.returncode == 0, (name, r.stderr)


def test_backup_pin_dump_clean():  # K-1: restore over a live db must be possible
    text = script("backup.sh")
    # --if-exists: a bare --clean (plain DROP) aborts an empty-db restore
    assert "pg_dump --clean --if-exists" in text
    assert "set -euo pipefail" in text
    # a failed pipeline must remove the incomplete archive, not leave it behind
    assert 'rm -f "$OUT_FILE"' in text
    assert "gzip -t" in text  # integrity check at backup time, not restore time


def test_restore_pin_on_error_stop_and_guard():
    text = script("restore.sh")
    assert "set -euo pipefail" in text
    assert "ON_ERROR_STOP=1" in text  # a half-loaded database is not a success
    # pin the EXECUTED confirmation branch, not the word in usage text
    assert "--yes) CONFIRMED=1 ;;" in text
    assert "RESTORE_YES" in text
    assert "psql" in text and "-U llmgate" in text


def test_smoke_pin_fail_loud_and_no_key_leak():
    import re
    text = script("smoke.sh")
    # the key travels in headers: no shell tracing command (a comment
    # mentioning "set -x" is fine -- an executed `set -x` is not)
    assert not re.search(r"^\s*set\s+-[a-zA-Z]*x", text, re.MULTILINE)
    # pin the EXECUTED fallback, not the "CODE=000" mention in a comment
    assert '|| CODE=000' in text  # network failure reports FAIL, not a crash
    assert "--max-time" in text  # every request is bounded
    assert "SMOKE_KEY is not set" in text and "exit 2" in text  # guard
