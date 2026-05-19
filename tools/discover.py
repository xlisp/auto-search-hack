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

# Small, deliberately conservative wordlist. Extend via --wordlist for serious work.
DEFAULT_WORDS = [
    "api", "v1", "v2", "users", "user", "me", "auth", "login", "logout",
    "register", "token", "refresh", "admin", "config", "health", "status",
    "metrics", "debug", "graphql", "search", "files", "upload", "download",
    "orders", "products", "items", "posts", "comments", "session", "profile",
]


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
        words = [w.strip() for w in Path(args.wordlist).read_text().splitlines() if w.strip()]
    elif auth_type in {"own_system", "ctf"} and scope.get("aggressive"):
        words = DEFAULT_WORDS
    elif auth_type in {"own_system", "ctf"}:
        words = DEFAULT_WORDS[:12]  # smaller default
    else:
        sys.stderr.write(
            "discover.py refuses default wordlist for bug_bounty/client_pentest. "
            "Provide --wordlist FILE matching engagement scope.\n"
        )
        sys.exit(2)

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
