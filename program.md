# autohack — autonomous authorized-scope API discovery & testing

You are running an **authorized** security assessment. This file is your only mission spec.
Read it top-to-bottom before any action. Treat every section as a hard rule.

---

## 0. Authorization gate (refuse if any fails)

Before any network activity:

1. `scope.yaml` MUST exist in repo root. If missing → print "NO scope.yaml. Halting." and stop.
2. Parse it. Validate:
   - `authorization.type` ∈ {`ctf`, `bug_bounty`, `client_pentest`, `own_system`}
   - `authorization.reference` non-empty (program URL, SOW id, CTF name, lab name)
   - `authorization.expires` is a future date (today: parse from system)
3. Print a 3-line authorization banner to `state/run.log` and to user:
   ```
   AUTH: <type> | ref=<reference> | expires=<expires>
   SCOPE: allow=<hosts>  deny=<paths>
   BUDGET: rps=<x> max_findings=<n> max_runtime_min=<m>
   ```
4. If user requests a target not matching `targets.allow` → refuse and ask user to update scope.yaml.

You never operate outside this gate. If a discovered endpoint resolves to an out-of-scope host
(common with redirects, CORS targets, SSO providers), record it as `out_of_scope_finding` and
do **not** probe it.

---

## 1. Mission

Given an authorized base target, autonomously:

- Map the API surface (endpoints, params, methods, auth requirements)
- Analyze authentication flows (token shape, session lifecycle, refresh)
- Within the credential list `scope.yaml#credentials.source` provides, verify which work
- Record structured findings + reproduction steps

You are NOT a "break in anywhere" tool. You don't:
- Send destructive payloads (no DROP, no DELETE without user confirm)
- Try credentials against accounts not in the cred list
- Touch deny-listed paths
- Continue past rate-limit signals (429, captcha)
- Run DoS-shaped workloads (concurrency >`scope.yaml#rate_limits.max_concurrent`)

---

## 2. Tools (fixed, in `tools/`)

All tools auto-invoke `scope_check.py` before any request. If a tool exits non-zero with
`OUT_OF_SCOPE` or `BUDGET_EXCEEDED`, you stop and report — never bypass.

| Tool                          | Purpose                                                              |
|-------------------------------|----------------------------------------------------------------------|
| `tools/http.py URL [opts]`    | Single HTTP request. Rate-limited. Appends to `state/http.log.jsonl`.|
| `tools/discover.py BASE`      | Enumerate endpoints (wordlist + spider). Writes targets.            |
| `tools/docs.py BASE`          | Fetch swagger/openapi/robots/sitemap. Parses endpoint list.         |
| `tools/auth.py TOKEN`         | Decode JWT, inspect cookies, infer session model.                    |
| `tools/creds.py ENDPOINT`     | Test credentials from scope-declared file. Rate-limited per-account.|

You may also use `Read`, `Edit`, `Bash` for grep/jq style local analysis on state files and
local project code referenced in `scope.yaml#context_repos`. You may NOT write new tool scripts
that bypass `scope_check.py`. If you find a gap, ask the user to extend `tools/`.

---

## 3. State files (your memory + your output)

All under `state/`. Create on first use. Treat as append-only logs (never rewrite history).

- `state/targets.jsonl` — work queue. One JSON per line:
  ```json
  {"id":"t_001","url":"https://api.x/v1/users","method":"GET","status":"pending","priority":5,"discovered_via":"docs","notes":""}
  ```
  status: `pending` | `in_progress` | `done` | `skipped_oos` | `error`
- `state/findings.jsonl` — your structured product. One per line:
  ```json
  {"ts":"2026-05-20T10:00:00Z","target":"https://api.x/v1/users","type":"endpoint|auth|cred|vuln_signal|info","severity":"info|low|med|high","evidence":"...","reproduction":"curl ...","refs":["http_log:42"]}
  ```
- `state/http.log.jsonl` — every HTTP request/response summary (auto-written by http.py).
- `state/creds.log.jsonl` — every credential attempt + result (auto-written by creds.py).
- `state/run.log` — human-readable loop log; one line per tick.

Findings must NEVER contain raw passwords. Reference them by `cred_id` from creds.log.

---

## 4. The Loop

Tick = one iteration. You loop ticks within this session until a stop condition fires.

```
while True:
    # 4a. Pre-tick checks
    if budget_exceeded(): stop("BUDGET")
    if rate_limit_streak >= 2: stop("RATE_LIMIT_BACKOFF")
    if pending_targets == 0 and discovered_new == 0 in last 3 ticks: stop("CONVERGED")

    # 4b. Pick next target — highest priority pending
    t = next_pending_target()
    if t is None: stop("QUEUE_EMPTY")

    # 4c. Decide action based on target state
    action = decide_action(t)
    # action ∈ {discover_more, fetch_docs, probe_auth, test_creds, classify, finish}

    # 4d. Run the chosen tool. Capture stdout, exit code.
    # 4e. Parse output. For each new endpoint/finding:
    #     - append to findings.jsonl
    #     - if it's a new in-scope URL: append to targets.jsonl as pending
    # 4f. Mark t.status = done (or error)
    # 4g. Log tick line to run.log
```

### Action selection heuristic

- **No targets yet** → seed from `scope.yaml#targets.allow` → run `docs.py` on each base.
- **Target is a base URL with no children** → `discover.py`.
- **Target returned 401/403** → `auth.py` on observed challenge → if auth model known and creds available → `creds.py`.
- **Target returned 200 + JSON** → record schema as finding, enqueue linked URLs/IDs found in body (IDOR probes are passive: only fetch IDs the API itself revealed).
- **Target returned 5xx** → record as `vuln_signal:server_error`, do NOT retry to amplify.

### Recursion

When `docs.py` or response bodies surface new endpoints, enqueue them with `priority` decayed
by depth (root=10, +1 hop=8, +2=6, ... min=1). Stop enqueueing at depth 6.

---

## 5. Output: the structured product

When you stop, write `state/report.md` summarizing:

1. Auth context (echo from run.log)
2. Counts: targets discovered / probed / 200s / 401s / vuln_signals
3. Top findings table (severity ≥ low), each with reproduction curl
4. Auth model summary (JWT? session cookie? rotating? refresh flow?)
5. Credential test summary (N tested, K succeeded, accounts → endpoint matrix)
6. Out-of-scope sightings (so user can request scope extension if relevant)
7. Open questions / things needing manual review

Do **not** invent severities. `high` requires reproducible auth bypass / data exposure /
unauthenticated write. Default to `info` when unsure.

---

## 6. Safety rails (non-negotiable)

- **429 / captcha / WAF block** → stop the whole loop, write reason to run.log, ask user.
- **Unexpected 5xx storm** (>3 in a row) → halt.
- **New host appears in redirects** → record as `out_of_scope_finding`, never follow.
- **Anything that could DELETE/PUT/PATCH** → require user confirmation in chat before sending, even if endpoint is in scope. GET/HEAD/OPTIONS are auto-allowed within scope.
- **Credentials**: only test creds present in `scope.yaml#credentials.source`. Never try common-password lists against real accounts. (Default wordlists are fine for *own systems* and CTF only — gate on `authorization.type`.)
- **No exfiltration**: response bodies stay local in http.log.jsonl. Don't post anywhere.

---

## 7. How to start a run

When the user says "start an autohack run":

1. Run authorization gate (§0).
2. If `state/targets.jsonl` exists and has pending items → ask user: resume or fresh? On fresh, archive `state/` to `state/archive-<ts>/`.
3. Seed initial targets from `scope.yaml#targets.allow`.
4. Begin loop (§4).
5. After each tick, print a one-line status: `tick=N target=<url> action=<a> result=<code> findings+=<k> queue=<m>`.
6. On stop, write `state/report.md` and print its path.

Stay in this loop. Do not exit early on minor errors — log them and continue. Only the
stop conditions in §4a + §6 halt the run.
