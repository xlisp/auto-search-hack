#!/usr/bin/env python3
"""graphql.py — GraphQL introspection.

If GraphQL is exposed (common paths: /graphql /api/graphql /v1/graphql /query),
runs the standard introspection query and enumerates Query / Mutation / Subscription
operations.

Many production deployments disable introspection — a 400/403/empty response is
recorded as "introspection_disabled" (still useful info).

Usage:
    python3 tools/graphql.py BASE_URL
"""
from __future__ import annotations
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HTTP = [sys.executable, str(ROOT / "tools/http.py")]

CANDIDATES = ["/graphql", "/api/graphql", "/v1/graphql", "/query", "/graphiql"]

INTROSPECTION = (
    "query IntrospectionQuery { __schema { "
    "queryType{name} mutationType{name} subscriptionType{name} "
    "types { name kind fields { name } } } }"
)


def post_json(url: str, payload: dict) -> dict | None:
    r = subprocess.run(
        HTTP + [url, "--method", "POST",
                "--header", "Content-Type: application/json",
                "--data", json.dumps(payload),
                "--confirm-destructive"],
        capture_output=True, text=True,
    )
    if r.returncode == 7:
        sys.stderr.write("429 — halting graphql\n"); sys.exit(7)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def main() -> None:
    if len(sys.argv) != 2:
        sys.stderr.write("usage: graphql.py <BASE_URL>\n"); sys.exit(2)
    base = sys.argv[1].rstrip("/")
    for c in CANDIDATES:
        url = base + c
        resp = post_json(url, {"query": INTROSPECTION})
        if not resp:
            continue
        code = resp.get("code", 0)
        if code in (200, 201) and "__schema" in resp.get("body", ""):
            try:
                data = json.loads(resp["body"])
                schema = data["data"]["__schema"]
            except (KeyError, json.JSONDecodeError):
                print(json.dumps({"kind": "graphql_endpoint", "url": url,
                                  "note": "responded but schema parse failed"}))
                continue
            q = (schema.get("queryType") or {}).get("name")
            m = (schema.get("mutationType") or {}).get("name")
            s = (schema.get("subscriptionType") or {}).get("name")
            ops = []
            for t in schema.get("types") or []:
                if t.get("name") in (q, m, s) and t.get("fields"):
                    for f in t["fields"]:
                        ops.append({"type": t["name"], "op": f["name"]})
            print(json.dumps({
                "kind": "graphql_endpoint", "url": url,
                "introspection": "open",
                "query_type": q, "mutation_type": m, "subscription_type": s,
                "operations_count": len(ops),
                "operations_preview": ops[:25],
            }))
            return
        if code in (200, 400, 403, 404):
            # Endpoint responds but introspection blocked
            body = (resp.get("body") or "")[:200]
            if any(s in body.lower() for s in ["graphql", "query", "introspection"]):
                print(json.dumps({"kind": "graphql_endpoint", "url": url,
                                  "introspection": "disabled_or_filtered",
                                  "code": code, "body_snippet": body}))
                return


if __name__ == "__main__":
    main()
