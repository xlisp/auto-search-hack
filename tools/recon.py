#!/usr/bin/env python3
"""recon.py — local source/config static analysis.

Walks every path in scope.yaml#context_repos and extracts:

- Route definitions:
    Flask          @app.route("/x")  / @bp.route(...)
    FastAPI        @app.get("/x")  /  @router.post(...)
    Express        app.get('/x', ..)  / router.post(...)
    Django         path("x/", ..)  / re_path(r"^x$", ..)
    Rails          get '/x' / post '/x' / resources :x (routes.rb)
    Spring (Java)  @GetMapping("/x")  /  @RequestMapping("/x")
    .proto         rpc Foo (...)  returns (...)
- Hardcoded URLs in any text file (https?://...)
- Likely secret / auth hints (env keys containing TOKEN | SECRET | KEY | JWT | AUTH | PASS)
  — never prints the value, only file:line + key name
- Pointers to local API docs (openapi.yaml|json, swagger.json, *.postman_collection.json,
  README.md / API.md / docs/*)

No network activity. Output is JSONL on stdout — one record per finding.
Run before any HTTP work to seed targets.jsonl.

Usage:
    python3 tools/recon.py             # uses scope.yaml#context_repos
    python3 tools/recon.py PATH [PATH...]   # explicit override
"""
from __future__ import annotations
import sys
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", "target", ".next", ".idea", ".vscode", "vendor"}
TEXT_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rb", ".java", ".kt",
             ".cs", ".rs", ".php", ".scala", ".clj", ".ex", ".exs", ".yaml",
             ".yml", ".json", ".toml", ".ini", ".env", ".conf", ".md", ".txt",
             ".html", ".vue", ".svelte", ".proto", ".graphql", ".gql"}

# (framework, regex, has_method_group, has_path_group_index)
ROUTE_PATTERNS = [
    ("flask",   re.compile(r"""@\s*\w+\.route\(\s*['"]([^'"]+)['"](?:[^)]*methods\s*=\s*\[([^\]]+)\])?""")),
    ("fastapi", re.compile(r"""@\s*\w+\.(get|post|put|patch|delete|head|options)\(\s*['"]([^'"]+)['"]""", re.I)),
    ("express", re.compile(r"""\b(?:app|router|server)\.(get|post|put|patch|delete|head|all|use)\s*\(\s*['"`]([^'"`]+)['"`]""", re.I)),
    ("django",  re.compile(r"""\b(?:path|re_path)\(\s*['"r]+([^'")]+)['"]""")),
    ("rails",   re.compile(r"""^\s*(get|post|put|patch|delete|match)\s+['"]([^'"]+)['"]""", re.M | re.I)),
    ("spring",  re.compile(r"""@\s*(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*)?['"]([^'"]+)['"]""")),
    ("proto",   re.compile(r"""\brpc\s+(\w+)\s*\(""")),
]

URL_RE = re.compile(r"""https?://[^\s'"`<>)]+""")
SECRET_KEY_RE = re.compile(
    r"""^\s*(?:export\s+)?([A-Z][A-Z0-9_]*(?:TOKEN|SECRET|KEY|JWT|AUTH|PASS|PWD)[A-Z0-9_]*)\s*[:=]""",
    re.M | re.I,
)
DOC_FILE_NAMES = {"openapi.yaml", "openapi.yml", "openapi.json", "swagger.json",
                  "swagger.yaml", "api.md", "api-spec.md", "readme.md"}


def load_context_repos() -> list[Path]:
    try:
        import yaml
        s = yaml.safe_load((ROOT / "scope.yaml").read_text())
    except Exception:
        return []
    repos = s.get("context_repos") or []
    out = []
    for r in repos:
        p = Path(r).expanduser()
        if p.is_dir():
            out.append(p)
    return out


def walk(root: Path):
    for p in root.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        if p.suffix.lower() not in TEXT_EXTS and p.name.lower() not in DOC_FILE_NAMES:
            continue
        try:
            yield p, p.read_text(errors="ignore")
        except (PermissionError, OSError):
            continue


def emit(rec: dict) -> None:
    print(json.dumps(rec))


def scan_file(path: Path, text: str) -> None:
    rel = str(path)
    # Routes
    for framework, pat in ROUTE_PATTERNS:
        for m in pat.finditer(text):
            line = text[:m.start()].count("\n") + 1
            groups = m.groups()
            if framework == "fastapi":
                method, p = groups[0].upper(), groups[1]
            elif framework == "express":
                method, p = groups[0].upper(), groups[1]
            elif framework == "spring":
                method, p = (groups[0].upper() + "*"), groups[1]  # Request -> any
            elif framework == "rails":
                method, p = groups[0].upper(), groups[1]
            elif framework == "flask":
                p, methods = groups[0], (groups[1] or "GET")
                method = re.sub(r"[\s'\"]+", "", methods).split(",")[0].upper() or "GET"
            elif framework == "django":
                method, p = "GET", groups[0]
            elif framework == "proto":
                method, p = "RPC", groups[0]
            else:
                continue
            emit({"kind": "route", "framework": framework, "method": method,
                  "path": p, "source": f"{rel}:{line}"})
    # URLs
    for m in URL_RE.finditer(text):
        url = m.group(0).rstrip(".,);]}\"'")
        line = text[:m.start()].count("\n") + 1
        emit({"kind": "url", "url": url, "source": f"{rel}:{line}"})
    # Secret hints — env-style keys
    if path.suffix.lower() in {".env", ".ini", ".conf", ".yaml", ".yml", ".toml", ".json"} \
            or path.name.startswith(".env"):
        for m in SECRET_KEY_RE.finditer(text):
            line = text[:m.start()].count("\n") + 1
            emit({"kind": "secret_hint", "key": m.group(1), "source": f"{rel}:{line}",
                  "note": "key name suggests secret/credential — VALUE NOT EXTRACTED"})
    # Doc file pointers
    if path.name.lower() in DOC_FILE_NAMES:
        emit({"kind": "doc_pointer", "path": rel, "note": "review for endpoint hints"})


def main() -> None:
    if len(sys.argv) > 1:
        roots = [Path(a).expanduser() for a in sys.argv[1:] if Path(a).expanduser().is_dir()]
    else:
        roots = load_context_repos()
    if not roots:
        sys.stderr.write("No context_repos in scope.yaml (and no path args). Nothing to recon.\n")
        sys.exit(0)
    for r in roots:
        for path, text in walk(r):
            scan_file(path, text)


if __name__ == "__main__":
    main()
