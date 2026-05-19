#!/usr/bin/env python3
"""Credential tester. Strictly scope-gated; passwords never stored in logs.

Modes (mutually exclusive):

  pairs (default)
      Reads scope.yaml#credentials.source — one `user:pass` per line.
      Always allowed regardless of authorization.type — this is the
      "I have specific creds to test" mode.

  combo
      --user-list FILE  --pass-list FILE
      Cartesian product. ALLOWED only for own_system / ctf, OR when
      scope.yaml#aggressive_credentials is true (for bug_bounty/client_pentest).

  common
      --common-passwords            (uses tools/wordlists/common-passwords.txt)
      [--users alice,bob OR --user-list FILE]
      Tries the bundled common-password list. ALLOWED only for own_system / ctf,
      OR with explicit aggressive_credentials: true.

Per-account attempt cap is enforced from scope.yaml#credentials.max_attempts_per_account.

Usage:
    python3 tools/creds.py ENDPOINT --user-field u --pass-field p [mode flags]

  --method POST            HTTP method (default POST)
  --mode form|json         Body encoding (default json)
  --success-code 200       Status code that means "auth ok"
  --failure-snippet TEXT   Substring in body that means "failed" (even on 200)
  --capture-token-path X   JSON path (e.g. token, data.access_token) — saves the
                           winning token to state/tokens/<user>.txt for replay.py.
"""
from __future__ import annotations
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
TOKENS = STATE / "tokens"
LOG = STATE / "creds.log.jsonl"
HTTP = [sys.executable, str(ROOT / "tools/http.py")]
COMMON_PW = ROOT / "tools/wordlists/common-passwords.txt"


def load_scope() -> dict:
    import yaml
    return yaml.safe_load((ROOT / "scope.yaml").read_text())


def aggressive_allowed(scope: dict) -> bool:
    t = scope.get("authorization", {}).get("type")
    if t in {"own_system", "ctf"}:
        return True
    return bool(scope.get("aggressive_credentials"))


def read_list(path: str) -> list[str]:
    return [l.strip() for l in Path(path).read_text().splitlines()
            if l.strip() and not l.startswith("#")]


def read_pairs(path: Path) -> list[tuple[str, str]]:
    out = []
    for l in path.read_text().splitlines():
        l = l.strip()
        if not l or l.startswith("#") or ":" not in l:
            continue
        u, p = l.split(":", 1)
        out.append((u, p))
    return out


def extract_token(body: str, dotted: str) -> str | None:
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        return None
    for part in dotted.split("."):
        if not isinstance(obj, dict) or part not in obj:
            return None
        obj = obj[part]
    return obj if isinstance(obj, str) else None


def attempt(endpoint: str, user: str, pw: str, args, headers_extra: list[str]) -> dict:
    if args.mode == "json":
        body = json.dumps({args.user_field: user, args.pass_field: pw})
        ct = ["Content-Type: application/json"]
    else:
        from urllib.parse import urlencode
        body = urlencode({args.user_field: user, args.pass_field: pw})
        ct = ["Content-Type: application/x-www-form-urlencoded"]
    cmd = HTTP + [endpoint, "--method", args.method, "--data", body,
                  "--confirm-destructive"]
    for h in ct + headers_extra:
        cmd += ["--header", h]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 7:
        sys.stderr.write("429 — halting cred run.\n"); sys.exit(7)
    if r.returncode != 0:
        return {"error": r.stderr.strip()}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": "bad http.py output"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("endpoint")
    ap.add_argument("--user-field", required=True)
    ap.add_argument("--pass-field", required=True)
    ap.add_argument("--method", default="POST")
    ap.add_argument("--mode", choices=["form", "json"], default="json")
    ap.add_argument("--success-code", type=int, default=200)
    ap.add_argument("--failure-snippet", default=None)
    ap.add_argument("--capture-token-path", default=None,
                    help="Dotted path (e.g. token, data.access_token) to save tokens for replay.")
    ap.add_argument("--header", action="append", default=[],
                    help="Extra header to send (repeatable)")
    # Mode selectors
    ap.add_argument("--user-list", default=None)
    ap.add_argument("--pass-list", default=None)
    ap.add_argument("--users", default=None, help="Comma-separated usernames (with --common-passwords)")
    ap.add_argument("--common-passwords", action="store_true")
    args = ap.parse_args()

    scope = load_scope()
    creds_cfg = scope.get("credentials", {})
    cap = int(creds_cfg.get("max_attempts_per_account", 5))

    # Build (user, pw) iterable per mode
    if args.user_list and args.pass_list:
        if not aggressive_allowed(scope):
            sys.stderr.write(
                "combo mode (user-list × pass-list) blocked for this authorization.type. "
                "Set aggressive_credentials: true in scope.yaml to permit.\n"
            )
            sys.exit(2)
        users = read_list(args.user_list)
        passes = read_list(args.pass_list)
        pairs = [(u, p) for u in users for p in passes]
        mode_name = "combo"
    elif args.common_passwords:
        if not aggressive_allowed(scope):
            sys.stderr.write(
                "common-passwords mode blocked for this authorization.type. "
                "Set aggressive_credentials: true in scope.yaml to permit.\n"
            )
            sys.exit(2)
        if args.users:
            users = [u.strip() for u in args.users.split(",") if u.strip()]
        elif args.user_list:
            users = read_list(args.user_list)
        else:
            sys.stderr.write("--common-passwords needs --users or --user-list\n")
            sys.exit(2)
        passes = [l for l in COMMON_PW.read_text().splitlines()
                  if l.strip() and not l.startswith("#")]
        pairs = [(u, p) for u in users for p in passes]
        mode_name = "common"
    else:
        src = creds_cfg.get("source")
        if not src:
            sys.stderr.write("scope.yaml#credentials.source not set. Refusing.\n")
            sys.exit(2)
        creds_path = (ROOT / src) if not Path(src).is_absolute() else Path(src)
        if not creds_path.exists():
            sys.stderr.write(f"Cred file not found: {creds_path}\n"); sys.exit(2)
        pairs = read_pairs(creds_path)
        mode_name = "pairs"

    attempts_by_user: dict[str, int] = {}
    successes = 0
    for user, pw in pairs:
        attempts_by_user[user] = attempts_by_user.get(user, 0) + 1
        if attempts_by_user[user] > cap:
            continue
        cred_id = "c_" + uuid.uuid4().hex[:10]
        resp = attempt(args.endpoint, user, pw, args, args.header)
        if "error" in resp:
            continue
        code = resp.get("code", 0)
        body_text = resp.get("body", "")
        failed_marker = args.failure_snippet and (args.failure_snippet in body_text)
        success = (code == args.success_code) and not failed_marker
        token = None
        if success and args.capture_token_path:
            token = extract_token(body_text, args.capture_token_path)
            if token:
                TOKENS.mkdir(exist_ok=True)
                (TOKENS / f"{user}.txt").write_text(token)
        entry = {
            "cred_id": cred_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "mode": mode_name,
            "endpoint": args.endpoint,
            "user": user,
            "pw_len": len(pw),  # never log raw password
            "code": code,
            "success": success,
            "token_captured": bool(token),
            "log_id": resp.get("log_id"),
        }
        with LOG.open("a") as g:
            g.write(json.dumps(entry) + "\n")
        print(json.dumps(entry))
        if success:
            successes += 1
        time.sleep(0.2)

    sys.stderr.write(f"creds.py {mode_name}: tried={sum(attempts_by_user.values())} success={successes}\n")


if __name__ == "__main__":
    main()
