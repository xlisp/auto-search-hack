#!/usr/bin/env python3
"""Rate-limited, scope-checked, fully-logged HTTP fetch.

Usage:
    python3 tools/http.py <URL> [--method GET] [--header 'K: V']... [--data BODY]
Outputs JSON to stdout:
    {"url","method","code","headers","body","elapsed_ms","log_id"}
"""
import sys
import json
import time
import subprocess
import argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
STATE.mkdir(exist_ok=True)
LOG = STATE / "http.log.jsonl"

DESTRUCTIVE = {"DELETE", "PUT", "PATCH", "POST"}


def load_rps() -> float:
    import yaml
    s = yaml.safe_load((ROOT / "scope.yaml").read_text())
    return float(s.get("rate_limits", {}).get("requests_per_second", 2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--method", default="GET")
    ap.add_argument("--header", action="append", default=[])
    ap.add_argument("--data", default=None)
    ap.add_argument("--confirm-destructive", action="store_true",
                    help="Required for non-GET/HEAD/OPTIONS methods.")
    args = ap.parse_args()

    method = args.method.upper()
    if method in DESTRUCTIVE and not args.confirm_destructive:
        sys.stderr.write(
            f"REFUSED: {method} requires --confirm-destructive "
            "(and explicit user confirmation per program.md §6)\n"
        )
        sys.exit(5)

    # Scope check
    r = subprocess.run(
        [sys.executable, str(ROOT / "tools/scope_check.py"), args.url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        sys.exit(r.returncode)

    # Rate limit
    rps = load_rps()
    time.sleep(max(0.0, 1.0 / rps))

    cmd = ["curl", "-sS", "-i", "--max-time", "20",
           "-X", method,
           "-w", "\n__META__:%{http_code}|%{time_total}\n",
           args.url]
    for h in args.header:
        cmd += ["-H", h]
    if args.data is not None:
        cmd += ["--data", args.data]

    t0 = time.monotonic()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    raw = proc.stdout
    code = 0
    if "__META__:" in raw:
        meta = raw.rsplit("__META__:", 1)[1].strip()
        try:
            code = int(meta.split("|")[0])
        except ValueError:
            code = 0
        raw = raw.rsplit("__META__:", 1)[0]
    # Split headers / body (first blank line)
    headers, _, body = raw.partition("\r\n\r\n")
    if not body:
        headers, _, body = raw.partition("\n\n")

    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_id = sum(1 for _ in LOG.open()) + 1 if LOG.exists() else 1
    log_entry = {
        "log_id": log_id, "ts": ts, "url": args.url, "method": method,
        "code": code, "elapsed_ms": elapsed_ms,
        "req_headers": args.header,
        "resp_headers_len": len(headers),
        "resp_body_len": len(body),
    }
    with LOG.open("a") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Full body returned on stdout (for agent parsing); not persisted to keep log slim.
    out = {
        "url": args.url, "method": method, "code": code,
        "elapsed_ms": elapsed_ms, "log_id": log_id,
        "headers": headers, "body": body[:200_000],  # cap
        "body_truncated": len(body) > 200_000,
    }
    print(json.dumps(out))

    if code == 429:
        sys.stderr.write("RATE_LIMIT_HIT (429) — agent should halt loop per §6\n")
        sys.exit(7)


if __name__ == "__main__":
    main()
