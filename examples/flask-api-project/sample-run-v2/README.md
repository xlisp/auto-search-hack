# sample-run-v2 — baseline artifacts from the upgraded pipeline

Captured: 2026-05-20, against `app.py` running on `127.0.0.1:5050`.

This is the **new** baseline that demonstrates the full upgraded pipeline:
static recon → docs/spider → wordlist discovery → cred testing with token
capture → JWT replay → structured report.

Use it to regression-test tool changes and to see what a healthy run produces.

## Files

| File              | What's new vs v1                                                          |
|-------------------|---------------------------------------------------------------------------|
| `recon.jsonl`     | **NEW** — 17 records from `recon.py`: 9 routes, 6 URLs, 2 doc pointers     |
| `targets.jsonl`   | Work queue (same as v1 — 8 targets from openapi + /health)                |
| `findings.jsonl`  | **30 findings** (was 18) — adds 12 `auth_replay` records from `replay.py` |
| `http.log.jsonl`  | **83 requests** (was 58) — includes replay traffic                        |
| `creds.log.jsonl` | **14 attempts** (was 7) — second pass uses `--capture-token-path token`,  |
|                   | `token_captured: true` on 3 successes                                     |
| `creds.txt`       | Input cred list (unchanged)                                               |
| `report.md`       | Regenerated with **Phase 0 recon section + JWT replay section**           |

## What's NOT here (intentionally)

`state/tokens/` is **not** archived. Even though the demo's HS256 secret is
publicly written in `app.py` and tokens expire after 1h, JWTs go in `.gitignore`
and stay there. They're produced at runtime; replicate the run to regenerate.

## Reproduce

```bash
# from repo root, with Flask target running on :5050
cp examples/flask-api-project/scope.yaml ./scope.yaml
cp examples/flask-api-project/creds.txt  ./state/creds.txt
export NO_PROXY="127.0.0.1,localhost"
# in Claude Code: "look at program.md and start an autohack run"
```

## Key v2 findings to expect

- 🔴 **high — cred**: 3 valid logins (alice / bob / admin)
- 🔴 **high — vuln_signal**: `/admin/users` reachable with admin JWT
- 🔴 **high — auth_replay**: admin JWT → `/admin/users` = 200 (expected for admin
  but the tool flags it because the path matches `/admin/*` — a real engagement
  would investigate whether admin auth is over-permissive)
- 🟡 **med — auth**: HS256 + `role` claim trusted by backend
- ℹ️  **info — auth_replay**: alice's user JWT → `/admin/users` = **403** (proper
  boundary, recorded as info — this is the GOOD outcome; if it were 200, it would
  be high-severity vertical privilege escalation)
- ✓ scope guard blocks `/admin/secret` (deny list)
- ✓ no plaintext passwords anywhere in `state/`
- ✓ 9 routes extracted from source via `recon.py` — matches the network surface
  found by `docs.py`, validating the static-analysis path
