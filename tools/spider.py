#!/usr/bin/env python3
"""spider.py — fetch a page, extract endpoint candidates from HTML + JS.

Pulls URLs from:
  - <a href>, <form action>, <link href>, <script src>, <img src>
  - JS strings inside <script>...</script> (regex-based, conservative)
  - fetch(...) / axios.{get,post,put,delete,patch}(...) call sites in JS
  - obvious API path patterns ('/api/...', '/v1/...', '/graphql', '/rest/...')

Resolves relative URLs against the page URL. Emits JSONL of unique candidates.
Each candidate runs through scope_check.py before being printed — out-of-scope
URLs are emitted with kind=oos_sighting so the agent can record them safely.

Usage:
    python3 tools/spider.py https://app.example.com/
"""
from __future__ import annotations
import sys
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]
SCOPE_CHECK = [sys.executable, str(ROOT / "tools/scope_check.py")]

HREF_RE = re.compile(r"""\b(?:href|src|action)\s*=\s*['"]([^'"]+)['"]""", re.I)
JS_FETCH_RE = re.compile(r"""\bfetch\s*\(\s*['"`]([^'"`]+)['"`]""")
JS_AXIOS_RE = re.compile(r"""\baxios(?:\.\w+)?\s*\(\s*\{?\s*(?:url\s*:\s*)?['"`]([^'"`]+)['"`]""")
JS_PATH_RE  = re.compile(r"""['"`](/[a-zA-Z0-9_\-./{}:]+(?:\?[^'"`]*)?)['"`]""")


def fetch(url: str) -> dict | None:
    r = subprocess.run(HTTP + [url], capture_output=True, text=True)
    if r.returncode == 7:
        sys.stderr.write("429 — halting spider\n")
        sys.exit(7)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def in_scope(url: str) -> bool:
    return subprocess.run(SCOPE_CHECK + [url], capture_output=True).returncode == 0


def extract(body: str, base: str) -> set[str]:
    found = set()
    for rx in (HREF_RE, JS_FETCH_RE, JS_AXIOS_RE):
        for m in rx.finditer(body):
            found.add(m.group(1))
    # Conservative path-like strings (filter obvious junk)
    for m in JS_PATH_RE.finditer(body):
        p = m.group(1)
        if any(seg in p for seg in ["/api", "/v1", "/v2", "/graphql", "/rest", "/auth", "/login"]):
            found.add(p)
    # Resolve + normalize
    norm = set()
    for u in found:
        if u.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        norm.add(urljoin(base, u))
    return norm


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: spider.py <URL>\n")
        sys.exit(2)
    base = sys.argv[1]
    resp = fetch(base)
    if not resp:
        sys.exit(1)
    urls = extract(resp.get("body", ""), base)
    for u in sorted(urls):
        kind = "endpoint" if in_scope(u) else "oos_sighting"
        host = urlparse(u).hostname or ""
        print(json.dumps({"kind": kind, "url": u, "host": host, "discovered_via": "spider"}))


if __name__ == "__main__":
    main()
