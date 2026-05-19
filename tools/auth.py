#!/usr/bin/env python3
"""Auth analyzer. Passive — does not send requests.

Subcommands:
    jwt TOKEN        — decode JWT header/payload, flag weak alg, expiry, scope claims.
    cookie 'K=V; K2=V2'  — inspect cookies for likely session/auth markers.
    challenge HEADERS_JSON_FILE  — given a 401/403 response headers dump, infer model.

All output is JSON to stdout.
"""
import sys
import json
import base64
from datetime import datetime, timezone


def b64url_decode(s: str) -> bytes:
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def jwt_decode(tok: str) -> dict:
    parts = tok.split(".")
    if len(parts) != 3:
        return {"error": "not a JWT (expect 3 parts)"}
    try:
        header = json.loads(b64url_decode(parts[0]))
        payload = json.loads(b64url_decode(parts[1]))
    except Exception as e:
        return {"error": f"decode failed: {e}"}
    flags = []
    if header.get("alg", "").lower() == "none":
        flags.append("alg_none")
    if header.get("alg", "").upper().startswith("HS"):
        flags.append("hmac_alg_check_secret_strength")
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        delta = exp - datetime.now(timezone.utc).timestamp()
        if delta < 0:
            flags.append("expired")
        if delta > 60 * 60 * 24 * 30:
            flags.append("very_long_lifetime")
    return {"header": header, "payload": payload, "flags": flags}


def cookie_inspect(cookie_str: str) -> dict:
    parts = [p.strip() for p in cookie_str.split(";") if p.strip()]
    cookies = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            cookies[k] = v
    auth_like = [k for k in cookies if any(s in k.lower() for s in
                 ["sess", "auth", "token", "jwt", "sid", "csrf", "xsrf"])]
    return {"cookies": list(cookies.keys()), "auth_like": auth_like}


def classify_challenge(headers_path: str) -> dict:
    raw = open(headers_path).read().lower()
    model = []
    if "www-authenticate: bearer" in raw:
        model.append("bearer_token")
    if "www-authenticate: basic" in raw:
        model.append("http_basic")
    if "set-cookie" in raw and "session" in raw:
        model.append("session_cookie")
    if "x-csrf" in raw or "csrf-token" in raw:
        model.append("csrf_enforced")
    if "location:" in raw and ("login" in raw or "auth" in raw):
        model.append("redirect_to_login")
    return {"model": model or ["unknown"]}


def main() -> None:
    if len(sys.argv) < 3:
        sys.stderr.write("usage: auth.py {jwt|cookie|challenge} ARG\n")
        sys.exit(2)
    cmd, arg = sys.argv[1], sys.argv[2]
    if cmd == "jwt":
        print(json.dumps(jwt_decode(arg)))
    elif cmd == "cookie":
        print(json.dumps(cookie_inspect(arg)))
    elif cmd == "challenge":
        print(json.dumps(classify_challenge(arg)))
    else:
        sys.stderr.write(f"unknown subcommand: {cmd}\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
