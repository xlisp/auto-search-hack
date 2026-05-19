#!/usr/bin/env python3
"""replay.py — replay a captured token against discovered endpoints.

Use case: after creds.py finds a working low-privilege login, replay its JWT
against admin/sensitive endpoints. If any return 200, that is broken-auth
(vertical privilege escalation) — a high-severity finding.

The token is read from --token-file (or --token); never from CLI args directly
into shell history if you can help it. Endpoints are read from a JSONL file
(typically state/targets.jsonl) or one per line.

Usage:
    python3 tools/replay.py --token-file state/token.txt \
        --targets state/targets.jsonl --label "alice_user_jwt"
"""
from __future__ import annotations
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]
STATE = ROOT / "state"


def load_targets(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if "url" in obj:
                out.append({"url": obj["url"], "method": obj.get("method", "GET")})
        except json.JSONDecodeError:
            out.append({"url": line, "method": "GET"})
    return out


def probe(url: str, method: str, token: str) -> dict | None:
    if method.upper() != "GET":  # replay is read-only by default
        return None
    cmd = HTTP + [url, "--header", f"Authorization: Bearer {token}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 7:
        sys.stderr.write("429 — halting replay\n"); sys.exit(7)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--token")
    g.add_argument("--token-file")
    ap.add_argument("--targets", required=True, help="JSONL or plain URL list")
    ap.add_argument("--label", default="replay", help="Tag for findings")
    args = ap.parse_args()

    token = args.token or Path(args.token_file).read_text().strip()
    if not token:
        sys.stderr.write("empty token\n"); sys.exit(2)
    targets = load_targets(Path(args.targets))

    findings_path = STATE / "findings.jsonl"
    STATE.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    for t in targets:
        r = probe(t["url"], t["method"], token)
        if r is None:
            continue
        code = r.get("code", 0)
        results.append({"url": t["url"], "code": code})
        # Find privilege boundary signals
        sev = "info"
        evidence = f"replay code={code}"
        if code == 200 and ("/admin" in t["url"] or "/internal" in t["url"]
                            or "/billing" in t["url"]):
            sev = "high"
            evidence = (f"label={args.label} JWT accessed sensitive endpoint "
                        f"{t['url']} (200). Vertical privilege escalation candidate.")
        elif code == 200:
            evidence = f"label={args.label} JWT valid on {t['url']} (200)"
            sev = "info"
        elif code == 401:
            evidence = f"401 — token rejected (token possibly revoked/expired)"
        elif code == 403:
            evidence = f"403 — token authenticated but not authorized (proper boundary)"
        with findings_path.open("a") as fd:
            fd.write(json.dumps({
                "ts": ts, "target": t["url"], "type": "auth_replay",
                "severity": sev, "evidence": evidence,
                "reproduction": f"curl -H 'Authorization: Bearer <{args.label}>' {t['url']}",
                "refs": [f"http_log:{r.get('log_id')}"],
            }) + "\n")
    # Summary on stdout
    print(json.dumps({"label": args.label, "tested": len(results),
                      "results": results}))


if __name__ == "__main__":
    main()
