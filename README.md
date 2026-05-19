# auto-search-hack

Autonomous, scope-gated **recon + authorized security testing** harness for Claude Code.

The primary job is *collection*: point it at a new system and it builds you a structured
picture of the API surface, the auth model, which supplied credentials work, and where
the privilege boundaries leak — in minutes instead of days. Exploitation is a secondary
outcome of doing recon thoroughly.

> ⚠️ **Authorized use only.** Bug bounty (in scope), client pentest with SOW, CTF, or
> your own systems / local lab. The tool refuses to run without a valid `scope.yaml`.

## Why this exists

When you join a new team, onboard onto a client engagement, or open a new CTF box, the
slow part is reverse-engineering the system: what endpoints exist, how auth works, which
of your test accounts unlocks what. This repo automates that loop:

- A persistent **skill spec** (`program.md`) tells Claude Code how to behave.
- A small set of **fixed tools** in `tools/` (each scope-checked) do the actual work.
- A **JSONL state directory** is both the agent's memory and the audit trail.
- Claude runs the **loop** described in `program.md` until convergence or budget.

You say "look at program.md and start an autohack run" — it goes.

## Architecture

```
program.md                # The agent skill — Claude reads this and runs the loop
scope.yaml                # REQUIRED. Authorization + targets + budgets. Gitignored.
tools/
  scope_check.py          # Authorization + scope guard. All other tools call it first.
  http.py                 # Rate-limited HTTP, full request log to state/http.log.jsonl
  recon.py                # Static source analysis on context_repos (no network!)
  docs.py                 # Probes /openapi /swagger /robots /sitemap /.well-known
  discover.py             # Wordlist endpoint enumeration (uses tools/wordlists/api-paths.txt)
  spider.py               # HTML/JS endpoint extraction (anchors, fetch, axios)
  graphql.py              # GraphQL introspection
  auth.py                 # Passive JWT / cookie / 401-challenge analysis
  creds.py                # Credential tester: pairs | combo | common-passwords modes
  replay.py               # Replay captured JWT against endpoints (broken-auth detection)
  harvest.py              # Token capability map — schema + sample data + curl/python snippets
  wordlists/
    api-paths.txt         # Default endpoint wordlist
    common-usernames.txt  # Only used on own_system / ctf (or aggressive_credentials)
    common-passwords.txt  # Only used on own_system / ctf (or aggressive_credentials)
state/                    # All output here, append-only JSONL + report.md
  targets.jsonl           # Work queue
  findings.jsonl          # Structured findings (the product)
  http.log.jsonl          # Every HTTP request summary
  creds.log.jsonl         # Credential attempts (pw_len only — passwords NEVER stored)
  tokens/<user>.txt       # Captured JWTs (gitignored) for replay.py / harvest.py
  capabilities.jsonl      # Token → endpoint capability map
  examples/<label>/*.md   # Ready-to-paste curl + python snippets per endpoint
  report.md               # Final human-readable report
examples/flask-api-project/
  app.py                  # Demo JWT-authenticated Flask target
  scope.yaml              # Example scope for the demo target
  creds.txt               # Demo cred list
  sample-run/             # Baseline artifacts from one successful run
```

## Setup

```bash
cp scope.example.yaml scope.yaml
$EDITOR scope.yaml          # set authorization, targets, budgets, context_repos
pip install pyyaml          # only runtime dep (flask/pyjwt are only for the demo)
# If testing creds:
echo "alice:hunter2" > state/creds.txt
```

## Run

In Claude Code, from this directory:

> Hi, look at program.md and start an autohack run.

Claude will:

1. Validate `scope.yaml` (refuse if missing/expired/invalid).
2. **Phase 0 static recon** on `context_repos` — extract routes from source, list config
   files holding `*_TOKEN` / `*_SECRET` keys (without reading values), point at local
   API docs. Free wins, no traffic generated.
3. Seed network targets from `scope.yaml#targets.allow`.
4. Loop: pick target → run appropriate tool → write findings → enqueue children.
5. When `creds.py` finds a valid login and captures a JWT, **automatically replay** it
   against all known endpoints to find broken-auth surfaces, then **harvest** the
   full capability map: each accessible endpoint gets a schema sketch, walked IDs,
   and a copy-paste curl/python snippet under `state/examples/<label>/`.
6. Stop on queue-empty, budget, 429, or your interrupt.
7. Write `state/report.md`.

## "I just got a token — what can it do?" workflow

This is the workflow that replaces hours of manual API exploration. After you
(or `creds.py`) capture a token:

```bash
# 1. Replay quickly says "200 here, 403 there"
python3 tools/replay.py --token-file state/tokens/alice.txt \
    --targets state/targets.jsonl --label alice_user

# 2. Harvest pulls actual data + builds ready-to-paste snippets
python3 tools/harvest.py --token-file state/tokens/alice.txt \
    --targets state/targets.jsonl --label alice_user --max-ids 3

# 3. Read what came back
cat state/examples/alice_user/api_users.md
```

Each `state/examples/<label>/<slug>.md` contains the schema, a truncated sample
response, and curl + python snippets — copy any one, paste into a terminal /
notebook, and you're calling the API. For a system with 80 endpoints, this turns
"a week of discovery" into "10 minutes of running the loop, then reading".

## Recon-first workflow (the "footprint collector")

If you have source access (your own system, your employer's, a client with code access):

```yaml
# scope.yaml
context_repos:
  - /Users/you/projects/target-service
  - /Users/you/projects/target-service-docs
```

`tools/recon.py` walks these paths and finds:

- **Routes** in Flask `@app.route`, FastAPI `@app.get`, Express `app.get(...)`, Django
  `path(...)`, Rails `routes.rb`, Spring `@GetMapping`, `.proto` `rpc`s.
- **Hardcoded URLs** anywhere in source/configs.
- **Names** of env keys matching `*_TOKEN|*_SECRET|*_KEY|*_JWT|*_AUTH|*_PASS` —
  the value is never read or printed, just the key name and `file:line`.
- **Doc files**: `openapi.yaml`, `swagger.json`, `*.postman_collection.json`, `API.md`,
  `README.md` — anything that maps the surface.

Result: the agent enters the network phase already knowing the shape of the system.

## Credential testing modes

| Mode    | Trigger flags                          | Authorization gate                                              |
|---------|----------------------------------------|------------------------------------------------------------------|
| `pairs` | default — reads `credentials.source`   | always allowed (you supply specific `user:pass` pairs to test)   |
| `combo` | `--user-list F --pass-list F`          | `own_system` / `ctf` only — OR `aggressive_credentials: true`    |
| `common`| `--common-passwords --users a,b`       | `own_system` / `ctf` only — OR `aggressive_credentials: true`    |

Bundled wordlists are deliberately tiny (smoke-test sized). For real engagements, supply
your own engagement-appropriate lists.

## Hard rules baked in

- No tool runs without `scope_check.py` passing.
- DELETE/PUT/PATCH/POST require `--confirm-destructive`; agent must also ask you in chat.
- 429 → halt the run, do not retry into a rate-limit storm.
- No default password lists for bug bounty / client pentest unless you explicitly opt in.
- Findings and creds log never contain raw passwords (only `pw_len` + `cred_id`).
- Out-of-scope hosts that appear via redirects / spider are *recorded* as `oos_sighting` and not probed.
- Captured tokens live in `state/tokens/` and are gitignored.

## Resuming

`state/` is append-only. If interrupted, re-run; Claude will offer to resume from
`state/targets.jsonl` or archive and start fresh.
