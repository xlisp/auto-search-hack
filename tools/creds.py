#!/usr/bin/env python3
"""Credential tester. Strictly scope-gated.

Tests ONLY credentials from scope.yaml#credentials.source (one user:pass per line).
Per-account attempt count is capped by scope.yaml#credentials.max_attempts_per_account.

Usage:
    python3 tools/creds.py ENDPOINT_URL --user-field FIELD --pass-field FIELD \
        [--method POST] [--mode form|json] [--success-code 200] [--failure-snippet TEXT]
"""
import sys
import json
import subprocess
import argparse
import time
import uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
STATE.mkdir(exist_ok=True)
LOG = STATE / "creds.log.jsonl"
HTTP = [sys.executable, str(ROOT / "tools/http.py")]


def load_scope():
    import yaml
    return yaml.safe_load((ROOT / "scope.yaml").read_text())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("endpoint")
    ap.add_argument("--user-field", required=True)
    ap.add_argument("--pass-field", required=True)
    ap.add_argument("--method", default="POST")
    ap.add_argument("--mode", choices=["form", "json"], default="json")
    ap.add_argument("--success-code", type=int, default=200)
    ap.add_argument("--failure-snippet", default=None,
                    help="If present in body, mark attempt as failed (even on 200).")
    args = ap.parse_args()

    scope = load_scope()
    creds_cfg = scope.get("credentials", {})
    src = creds_cfg.get("source")
    if not src:
        sys.stderr.write("scope.yaml#credentials.source not set. Refusing.\n")
        sys.exit(2)
    creds_path = (ROOT / src) if not Path(src).is_absolute() else Path(src)
    if not creds_path.exists():
        sys.stderr.write(f"Cred file not found: {creds_path}\n")
        sys.exit(2)
    cap = int(creds_cfg.get("max_attempts_per_account", 5))

    attempts_by_user: dict[str, int] = {}
    with creds_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            user, pw = line.split(":", 1)
            attempts_by_user[user] = attempts_by_user.get(user, 0) + 1
            if attempts_by_user[user] > cap:
                continue
            cred_id = "c_" + uuid.uuid4().hex[:10]
            if args.mode == "json":
                body = json.dumps({args.user_field: user, args.pass_field: pw})
                headers = ["Content-Type: application/json"]
            else:
                from urllib.parse import urlencode
                body = urlencode({args.user_field: user, args.pass_field: pw})
                headers = ["Content-Type: application/x-www-form-urlencoded"]
            cmd = HTTP + [args.endpoint, "--method", args.method, "--data", body,
                          "--confirm-destructive"]
            for h in headers:
                cmd += ["--header", h]
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 7:
                sys.stderr.write("429 — halting cred run.\n")
                sys.exit(7)
            if r.returncode != 0:
                sys.stderr.write(r.stderr)
                continue
            try:
                resp = json.loads(r.stdout)
            except json.JSONDecodeError:
                continue
            code = resp.get("code", 0)
            body_text = resp.get("body", "")
            failed_marker = args.failure_snippet and (args.failure_snippet in body_text)
            success = (code == args.success_code) and not failed_marker
            entry = {
                "cred_id": cred_id,
                "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "endpoint": args.endpoint,
                "user": user,
                "pw_len": len(pw),  # never log raw password
                "code": code,
                "success": success,
                "log_id": resp.get("log_id"),
            }
            with LOG.open("a") as g:
                g.write(json.dumps(entry) + "\n")
            print(json.dumps(entry))
            # Inter-attempt sleep (additional to http.py rate limit) for credential safety
            time.sleep(0.2)


if __name__ == "__main__":
    main()
