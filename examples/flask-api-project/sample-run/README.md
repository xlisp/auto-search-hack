# sample-run — baseline artifacts from one autohack run

Captured: 2026-05-20, against `app.py` running on `127.0.0.1:5050`.

Use this as a reference for what a healthy autohack run looks like, and to
diff future tool changes against (e.g. "did my refactor of `docs.py` regress
endpoint discovery?").

## Files

| File              | What's in it                                                           |
|-------------------|------------------------------------------------------------------------|
| `targets.jsonl`   | Work queue after seeding from openapi + /health                        |
| `findings.jsonl`  | 18 structured findings (3 high, 1 med, rest info)                      |
| `http.log.jsonl`  | 58 request summaries (200×10, 401×9, 404×39)                           |
| `creds.log.jsonl` | 7 credential attempts, 3 successes — passwords NEVER stored (pw_len only) |
| `creds.txt`       | Input cred list (alice/bob/admin with both wrong and right passwords)  |
| `report.md`       | Final structured report per `program.md §5`                            |

## Reproduce

```bash
# from repo root, with Flask target running on :5050
cp examples/flask-api-project/scope.yaml ./scope.yaml
cp examples/flask-api-project/creds.txt  ./state/creds.txt
export NO_PROXY="127.0.0.1,localhost"
# then in Claude Code: "look at program.md and start an autohack run"
```

## Notable findings to expect

- 🔴 **high — cred**: 3 valid logins (alice / bob / admin)
- 🔴 **high — vuln_signal**: `/admin/users` reachable with admin JWT
- 🟡 **med — auth**: HS256 + `role` claim trusted by backend
- ✓ scope guard correctly blocks `/admin/secret`
- ✓ no plaintext passwords anywhere in `state/`
