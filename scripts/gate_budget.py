#!/usr/bin/env python3
"""Claude Code statusline: remaining llm-gate budget for the current key.

Shows spend against the key's max_budget (plus tpm/rpm limits) straight from
the gateway, so a team member can see their quota without opening the UI.

Setup (per user):
  1. Put your virtual key in a file, chmod 600, e.g. ~/.llm-gate/vk.key
  2. Copy gate_budget.conf.example to gate_budget.conf next to this script
     (or point GATE_BUDGET_CONF at it) and set key_file / base_url.
  3. settings.json:
       "statusLine": {
         "type": "command",
         "command": "python3 /path/to/gate_budget.py"
       }

Limits themselves are managed by the gateway admin (/key/update or UI);
this script only reads them (GET /key/info with the key itself).
"""
import json
import os
import pathlib
import sys
import urllib.request

DEF_CONF = pathlib.Path(__file__).with_suffix(".conf")


def load_conf():
    path = pathlib.Path(os.environ.get("GATE_BUDGET_CONF", DEF_CONF))
    conf = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    conf.setdefault("base_url", "https://llm-gate.lab.governetics.ru")
    conf.setdefault("key_file", "~/.llm-gate/vk.key")
    conf.setdefault("key_env", "")  # alternative: read the key from this env var
    conf.setdefault("warn_pct", 20)  # color the line red below this % left
    conf.setdefault("label", "gate")
    return conf


def main():
    conf = load_conf()
    token = ""
    if conf["key_env"]:
        token = os.environ.get(conf["key_env"], "")
    if not token:
        kf = pathlib.Path(conf["key_file"]).expanduser()
        try:
            token = kf.read_text(encoding="utf-8").strip()
        except OSError:
            print(f"{conf['label']}: key file not found ({kf})")
            return
    if not token or token.startswith("PLACEHOLDER"):
        print(f"{conf['label']}: key file is a placeholder")
        return

    req = urllib.request.Request(
        conf["base_url"].rstrip("/") + "/key/info",
        headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            info = json.load(resp).get("info", {})
    except Exception as exc:  # network down must not break the statusline
        print(f"{conf['label']}: unreachable ({exc.__class__.__name__})")
        return

    spend = info.get("spend") or 0.0
    budget = info.get("max_budget")
    alias = info.get("key_alias") or conf["label"]
    limits = []
    if info.get("tpm_limit"):
        limits.append(f"{info['tpm_limit'] // 1000}k tpm")
    if info.get("rpm_limit"):
        limits.append(f"{info['rpm_limit']} rpm")
    tail = (" · " + " · ".join(limits)) if limits else ""

    if budget:
        left = max(budget - spend, 0.0)
        pct = int(left * 100 / budget) if budget else 0
        mark = "🔴" if pct <= conf["warn_pct"] else "🟢"
        print(f"{mark} {alias}: ${spend:.2f}/${budget:.0f} — {pct}% left{tail}")
    else:
        # No budget set: token spend is only visible with model prices
        # configured; otherwise show that the key is alive.
        print(f"🟢 {alias}: ${spend:.2f} (no budget cap){tail}")


if __name__ == "__main__":
    # Claude Code pipes session JSON on stdin; we do not need it (yet).
    try:
        sys.stdin.read()
    except Exception:
        pass
    main()
