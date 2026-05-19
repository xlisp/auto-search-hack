# auto-search-hack

Autonomous, scope-gated API discovery + authorized security testing harness for Claude Code.

**Authorized use only.** Bug bounty (in-scope), client pentest with SOW, CTF, or your own
systems / local lab. The tool refuses to run without a valid `scope.yaml`.

## Architecture

```
program.md          # The agent skill — Claude reads this and runs the loop
scope.yaml          # REQUIRED. Authorization + targets + budgets. Gitignored.
tools/
  scope_check.py    # Authorization + scope guard. All other tools call it first.
  http.py           # Rate-limited HTTP, logs every request to state/http.log.jsonl
  docs.py           # Probes /openapi.json /swagger /robots /sitemap /.well-known
  discover.py       # Wordlist endpoint discovery (gated by auth type)
  auth.py           # Passive JWT/cookie/challenge analysis
  creds.py          # Credential tester (only against user-supplied cred list)
state/              # All output here, append-only JSONL + report.md
```

## Setup

```bash
cp scope.example.yaml scope.yaml
$EDITOR scope.yaml          # set authorization, targets, budgets
pip install pyyaml          # only runtime dep
# If testing creds:
echo "alice:hunter2"  > state/creds.txt
```

## Run

In Claude Code, from this directory:

> Hi, look at program.md and start an autohack run.

Claude will:
1. Validate `scope.yaml` (refuse if missing/expired/invalid).
2. Seed targets from `scope.yaml#targets.allow`.
3. Loop: pick target → run appropriate tool → write findings → enqueue children.
4. Stop on queue-empty, budget, 429, or your interrupt.
5. Write `state/report.md`.

## Hard rules baked in

- No tool runs without `scope_check.py` passing.
- DELETE/PUT/PATCH/POST require `--confirm-destructive`; agent must ask you in chat too.
- 429 → halt the run, do not retry into a rate-limit storm.
- No default password lists, ever. Credential testing requires your own list.
- Findings never contain raw passwords (only `pw_len` + `cred_id` reference).
- Out-of-scope hosts that appear via redirects are *recorded* and not probed.

## Resuming

`state/` is append-only. If interrupted, re-run; Claude will offer to resume from
`state/targets.jsonl` or archive and start fresh.
