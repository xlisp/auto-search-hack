#!/usr/bin/env python3
"""Scope guard. Every tool calls this before any network activity.

Usage:
    python3 tools/scope_check.py <URL>
Exit codes:
    0 — in scope
    1 — out of scope (host not in allow, or path in deny)
    2 — scope.yaml missing/invalid
    3 — authorization expired
    4 — budget exceeded
"""
import sys
import os
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
SCOPE = ROOT / "scope.yaml"
STATE = ROOT / "state"


def load_yaml(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text())
    except ImportError:
        sys.stderr.write("PyYAML required: pip install pyyaml\n")
        sys.exit(2)
    except Exception as e:
        sys.stderr.write(f"scope.yaml parse error: {e}\n")
        sys.exit(2)


def path_match(pattern: str, p: str) -> bool:
    regex = "^" + re.escape(pattern).replace(r"\*", ".*") + "$"
    return re.match(regex, p) is not None


def check_budget(scope: dict) -> None:
    budget = scope.get("budget", {})
    http_log = STATE / "http.log.jsonl"
    findings = STATE / "findings.jsonl"
    if http_log.exists():
        n_req = sum(1 for _ in http_log.open())
        if n_req >= budget.get("max_requests", 10**9):
            sys.stderr.write(f"BUDGET_EXCEEDED: requests {n_req}\n")
            sys.exit(4)
    if findings.exists():
        n_find = sum(1 for _ in findings.open())
        if n_find >= budget.get("max_findings", 10**9):
            sys.stderr.write(f"BUDGET_EXCEEDED: findings {n_find}\n")
            sys.exit(4)


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: scope_check.py <URL>\n")
        sys.exit(2)
    url = sys.argv[1]
    if not SCOPE.exists():
        sys.stderr.write("NO scope.yaml — refusing.\n")
        sys.exit(2)
    scope = load_yaml(SCOPE)

    auth = scope.get("authorization", {})
    if auth.get("type") not in {"ctf", "bug_bounty", "client_pentest", "own_system"}:
        sys.stderr.write("Invalid authorization.type\n")
        sys.exit(2)
    if not auth.get("reference"):
        sys.stderr.write("Missing authorization.reference\n")
        sys.exit(2)
    exp = auth.get("expires")
    if exp:
        try:
            if date.fromisoformat(str(exp)) < date.today():
                sys.stderr.write(f"Authorization expired: {exp}\n")
                sys.exit(3)
        except ValueError:
            sys.stderr.write(f"Bad expires date: {exp}\n")
            sys.exit(2)

    check_budget(scope)

    parsed = urlparse(url if "://" in url else f"http://{url}")
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    path = parsed.path or "/"

    # Deny first
    for d in scope.get("targets", {}).get("deny", []) or []:
        if d.get("host") == host:
            for pat in d.get("paths", []) or []:
                if path_match(pat, path):
                    sys.stderr.write(f"OUT_OF_SCOPE: denied path {pat} for {host}\n")
                    sys.exit(1)

    # Allow
    for a in scope.get("targets", {}).get("allow", []) or []:
        if a.get("host") != host:
            continue
        if port not in (a.get("ports") or [80, 443]):
            continue
        for pat in a.get("paths", []) or ["/*"]:
            if path_match(pat, path):
                print(json.dumps({"in_scope": True, "host": host, "path": path}))
                return
    sys.stderr.write(f"OUT_OF_SCOPE: host={host} path={path}\n")
    sys.exit(1)


if __name__ == "__main__":
    main()
