#!/usr/bin/env python3
"""Endpoint enumeration by wordlist. In-scope only.

For own_system / ctf authorization: a small built-in wordlist is allowed.
For bug_bounty / client_pentest: requires --wordlist FILE explicitly provided
by the user (so the engagement scope decides aggressiveness).

Usage:
    python3 tools/discover.py BASE_URL [--wordlist FILE] [--depth 1]
Emits candidate endpoints (200/301/302/401/403) as JSONL.
"""
import sys
import json
import subprocess
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]
BUNDLED_WORDLIST = ROOT / "tools/wordlists/api-paths.txt"


def load_scope():
    import yaml
    return yaml.safe_load((ROOT / "scope.yaml").read_text())


def fetch(url: str) -> dict | None:
    r = subprocess.run(HTTP + [url], capture_output=True, text=True)
    if r.returncode != 0:
        # 7 == 429 from http.py; propagate by stopping
        if r.returncode == 7:
            sys.stderr.write("Halting discover on 429\n")
            sys.exit(7)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--wordlist", default=None)
    ap.add_argument("--depth", type=int, default=1)
    args = ap.parse_args()

    scope = load_scope()
    auth_type = scope.get("authorization", {}).get("type")
    if args.wordlist:
        words = [w.strip() for w in Path(args.wordlist).read_text().splitlines()
                 if w.strip() and not w.startswith("#")]
    else:
        # Endpoint enumeration is read-only — bundled list is allowed for all auth types,
        # but bug_bounty/client_pentest should usually supply an engagement-specific list.
        if auth_type in {"bug_bounty", "client_pentest"} and not scope.get("aggressive"):
            sys.stderr.write(
                "discover.py: bug_bounty/client_pentest typically wants --wordlist FILE "
                "matching engagement scope. Set aggressive: true in scope.yaml to use the "
                "bundled list anyway.\n"
            )
            sys.exit(2)
        words = [w.strip() for w in BUNDLED_WORDLIST.read_text().splitlines()
                 if w.strip() and not w.startswith("#")]
        if not scope.get("aggressive"):
            words = words[:30]  # smaller default if not aggressive

    base = args.base.rstrip("/")
    queue = [(base, 0)]
    seen = {base}
    while queue:
        cur, depth = queue.pop(0)
        for w in words:
            url = f"{cur}/{w}"
            resp = fetch(url)
            if not resp:
                continue
            code = resp.get("code", 0)
            if code in (200, 201, 204, 301, 302, 307, 308, 401, 403):
                rec = {"url": url, "method": "GET", "code": code,
                       "discovered_via": f"wordlist@depth{depth}"}
                print(json.dumps(rec))
                if depth + 1 < args.depth and url not in seen and code < 400:
                    seen.add(url)
                    queue.append((url, depth + 1))


if __name__ == "__main__":
    main()
