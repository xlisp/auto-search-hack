#!/usr/bin/env python3
"""harvest.py — given a captured token, exhaustively map what it can DO.

Where replay.py asks "does this token authenticate against endpoint X?" (yes/no),
harvest.py asks "given this token, what is the *full picture* of what's
accessible, what data shapes come back, and how do I reproduce each call?"

For each target endpoint:
  1. Send authenticated GET with the token.
  2. If 200 JSON: extract a schema sketch (top-level keys + value-type sketch).
  3. If the URL contains a path placeholder (`{id}`, `<int:pid>`, `:id`, `:slug`):
     pull candidate IDs from previously-harvested list responses (look for `id`,
     `uuid`, `slug`, `username`, `name` fields in array items) and crawl up to
     --max-ids IDs per template.
  4. Note privilege boundary: if a `/admin/*` or `/internal/*` path returns 200,
     emit a `high` finding in `findings.jsonl` (privilege escalation candidate).
  5. Generate copy-paste snippets (`curl`, `python+requests`) per endpoint and
     write them to `state/examples/<label>/<slug>.md`.
  6. Append a structured row to `state/capabilities.jsonl`.

The result is a "token capability map" — what does *this* token actually unlock,
with concrete reproduction for each call. This is the step that replaces hours
of manual API exploration after auth.

Usage:
    python3 tools/harvest.py --token-file state/tokens/admin.txt \\
        --targets state/targets.jsonl --label admin_jwt [--max-ids 3]
"""
from __future__ import annotations
import sys
import json
import argparse
import subprocess
import re
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]
STATE = ROOT / "state"
EXAMPLES = STATE / "examples"
CAPABILITIES = STATE / "capabilities.jsonl"
FINDINGS = STATE / "findings.jsonl"

PLACEHOLDER_RE = re.compile(r"""(\{[^/}]+\}|<[^/>]+>|:[a-zA-Z_]\w*)""")
ID_FIELDS = ("id", "uuid", "guid", "slug", "username", "name", "key", "code")
SENSITIVE_PATTERNS = ("/admin", "/internal", "/billing", "/private", "/root")


def fetch(url: str, token: str) -> dict | None:
    r = subprocess.run(
        HTTP + [url, "--header", f"Authorization: Bearer {token}"],
        capture_output=True, text=True,
    )
    if r.returncode == 7:
        sys.stderr.write("429 — halting harvest\n"); sys.exit(7)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def schema_sketch(obj, depth: int = 0) -> str:
    """Compact type sketch: e.g. {users: array<{id:int, username:string}>}"""
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        keys = list(obj.keys())[:8]
        return "{" + ", ".join(f"{k}: {schema_sketch(obj[k], depth+1)}" for k in keys) + "}"
    if isinstance(obj, list):
        if not obj:
            return "array<>"
        return f"array<{schema_sketch(obj[0], depth+1)}>"
    if isinstance(obj, bool):
        return "bool"
    if isinstance(obj, int):
        return "int"
    if isinstance(obj, float):
        return "float"
    if isinstance(obj, str):
        return "string"
    if obj is None:
        return "null"
    return type(obj).__name__


def extract_ids(body_obj) -> list[str]:
    """Walk a JSON response for ID-like values. Returns up to 20 candidates."""
    found = []

    def walk(o):
        if len(found) >= 20:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in ID_FIELDS and isinstance(v, (str, int)):
                    found.append(str(v))
                walk(v)
        elif isinstance(o, list):
            for item in o:
                walk(item)

    walk(body_obj)
    # Dedup preserving order
    seen, uniq = set(), []
    for f in found:
        if f not in seen:
            seen.add(f); uniq.append(f)
    return uniq


def slugify(url: str) -> str:
    s = re.sub(r"^https?://[^/]+", "", url) or "/"
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_")
    return s or "root"


def write_example(label: str, url: str, method: str, token_repr: str,
                  code: int, body_preview: str, sketch: str) -> Path:
    out_dir = EXAMPLES / label
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{slugify(url)}.md"
    md = [
        f"# {method} {url}\n",
        f"\n*Token label:* `{label}`  *Response code:* `{code}`\n\n",
        f"## Schema sketch\n\n```\n{sketch}\n```\n\n",
        f"## Sample response (truncated)\n\n```json\n{body_preview}\n```\n\n",
        "## Reproduce — curl\n\n```bash\n",
        f'TOKEN="$(cat state/tokens/{token_repr}.txt)"\n',
        f"curl -H \"Authorization: Bearer $TOKEN\" '{url}'\n",
        "```\n\n",
        "## Reproduce — python\n\n```python\nimport requests\n",
        f'token = open("state/tokens/{token_repr}.txt").read().strip()\n',
        f"r = requests.{method.lower()}('{url}', headers={{'Authorization': f'Bearer {{token}}'}})\n",
        "print(r.status_code)\nprint(r.json())\n```\n",
    ]
    out_file.write_text("".join(md))
    return out_file


def expand_placeholders(template: str, ids: list[str]) -> list[str]:
    """For a URL like /api/users/{id}, return concrete URLs by substituting ids."""
    if not PLACEHOLDER_RE.search(template):
        return [template]
    out = []
    for i in ids:
        out.append(PLACEHOLDER_RE.sub(str(i), template, count=1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--token")
    g.add_argument("--token-file")
    ap.add_argument("--targets", required=True)
    ap.add_argument("--label", required=True, help="Tag the capability map by token label")
    ap.add_argument("--max-ids", type=int, default=3,
                    help="Cap per-template ID substitutions to avoid floods")
    args = ap.parse_args()

    token = args.token or Path(args.token_file).read_text().strip()
    token_name = Path(args.token_file).stem if args.token_file else args.label
    targets = []
    for line in Path(args.targets).read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get("method", "GET").upper() == "GET" and "url" in obj:
                targets.append(obj["url"])
        except json.JSONDecodeError:
            targets.append(line)

    STATE.mkdir(exist_ok=True)
    EXAMPLES.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # First pass: harvest concrete (non-template) URLs to collect ID pool
    id_pool: list[str] = []
    concrete = [u for u in targets if not PLACEHOLDER_RE.search(u)]
    templates = [u for u in targets if PLACEHOLDER_RE.search(u)]

    summary = {"endpoints_200": 0, "endpoints_4xx": 0, "endpoints_5xx": 0,
               "examples_written": 0, "ids_harvested": 0,
               "privilege_escalation_candidates": []}

    def process_url(url: str) -> None:
        resp = fetch(url, token)
        if resp is None:
            return
        code = resp.get("code", 0)
        body_text = resp.get("body", "") or ""
        body_obj = None
        if "application/json" in resp.get("headers", "").lower() or body_text.lstrip().startswith(("{", "[")):
            try:
                body_obj = json.loads(body_text)
            except json.JSONDecodeError:
                pass
        sketch = schema_sketch(body_obj) if body_obj is not None else f"non-JSON ({len(body_text)} bytes)"
        preview = body_text[:600] + ("…" if len(body_text) > 600 else "")
        ids_here = extract_ids(body_obj) if body_obj is not None else []
        id_pool.extend(ids_here)

        if 200 <= code < 300:
            summary["endpoints_200"] += 1
            ex = write_example(args.label, url, "GET", token_name, code, preview, sketch)
            summary["examples_written"] += 1
            # Privilege check
            if any(p in url for p in SENSITIVE_PATTERNS):
                summary["privilege_escalation_candidates"].append(url)
                with FINDINGS.open("a") as fd:
                    fd.write(json.dumps({
                        "ts": ts, "target": url, "type": "auth_harvest",
                        "severity": "high",
                        "evidence": f"label={args.label} token returned 200 on sensitive path. "
                                    f"Schema: {sketch[:120]}",
                        "reproduction": str(ex.relative_to(ROOT)),
                        "refs": [f"http_log:{resp.get('log_id')}"],
                    }) + "\n")
        elif 400 <= code < 500:
            summary["endpoints_4xx"] += 1
        elif code >= 500:
            summary["endpoints_5xx"] += 1

        with CAPABILITIES.open("a") as cf:
            cf.write(json.dumps({
                "ts": ts, "label": args.label, "url": url, "code": code,
                "schema": sketch, "ids_extracted": ids_here[:10],
                "log_id": resp.get("log_id"),
            }) + "\n")

    for u in concrete:
        process_url(u)

    summary["ids_harvested"] = len(set(id_pool))
    seen = set(); ids_dedup = []
    for i in id_pool:
        if i not in seen:
            seen.add(i); ids_dedup.append(i)

    # Second pass: expand templates with discovered IDs
    for tmpl in templates:
        targets_for_template = expand_placeholders(tmpl, ids_dedup[:args.max_ids])
        for u in targets_for_template:
            process_url(u)

    print(json.dumps({"label": args.label, **summary}, indent=2))


if __name__ == "__main__":
    main()
