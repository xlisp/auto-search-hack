#!/usr/bin/env python3
"""Pull standard discovery surfaces from a base URL:
  /robots.txt, /sitemap.xml, /openapi.json, /openapi.yaml,
  /swagger.json, /swagger/v1/swagger.json, /.well-known/*, /api-docs

Parses any OpenAPI/Swagger doc found and emits endpoint candidates as JSONL.

Usage:
    python3 tools/docs.py https://api.example.com
"""
import sys
import json
import subprocess
import re
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]

PROBES = [
    "/robots.txt", "/sitemap.xml",
    "/openapi.json", "/openapi.yaml", "/openapi.yml",
    "/swagger.json", "/swagger/v1/swagger.json", "/v2/api-docs", "/api-docs",
    "/.well-known/openid-configuration", "/.well-known/security.txt",
]


def fetch(url: str) -> dict | None:
    r = subprocess.run(HTTP + [url], capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def parse_openapi(body: str, base: str) -> list[dict]:
    try:
        spec = json.loads(body)
    except json.JSONDecodeError:
        try:
            import yaml
            spec = yaml.safe_load(body)
        except Exception:
            return []
    if not isinstance(spec, dict) or "paths" not in spec:
        return []
    server = base
    if spec.get("servers"):
        s0 = spec["servers"][0].get("url", "")
        if s0.startswith("http"):
            server = s0.rstrip("/")
    out = []
    for path, ops in (spec.get("paths") or {}).items():
        if not isinstance(ops, dict):
            continue
        for method in ops:
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            out.append({
                "url": server + path,
                "method": method.upper(),
                "discovered_via": "openapi",
            })
    return out


def parse_robots(body: str, base: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        m = re.match(r"(?:Allow|Disallow|Sitemap)\s*:\s*(\S+)", line, re.I)
        if m:
            tok = m.group(1)
            url = tok if tok.startswith("http") else urljoin(base + "/", tok.lstrip("/"))
            out.append({"url": url, "method": "GET", "discovered_via": "robots"})
    return out


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: docs.py <BASE_URL>\n")
        sys.exit(2)
    base = sys.argv[1].rstrip("/")
    found: list[dict] = []
    for p in PROBES:
        resp = fetch(base + p)
        if not resp or resp.get("code", 0) >= 400:
            continue
        body = resp.get("body", "")
        if p.endswith((".json", ".yaml", ".yml")) or "swagger" in p or "openapi" in p or "api-docs" in p:
            found += parse_openapi(body, base)
        elif p == "/robots.txt":
            found += parse_robots(body, base)
        else:
            found.append({"url": base + p, "method": "GET", "discovered_via": "well_known"})
    # Dedup
    seen = set()
    uniq = []
    for f in found:
        k = (f["method"], f["url"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(f)
    for f in uniq:
        print(json.dumps(f))


if __name__ == "__main__":
    main()
