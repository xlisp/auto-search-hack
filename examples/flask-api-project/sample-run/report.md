# autohack report — examples/flask-api-project
## Authorization
- type: own_system
- ref: examples/flask-api-project (local demo)
- expires: 2099-12-31

## Counts
- HTTP requests: 58
- Unique endpoints discovered: 8
- Findings: 18
- Response codes: {200: 10, 404: 39, 401: 9}
- Cred attempts: 7 | successes: 3

## Top findings

| severity | type | target | evidence |
|---|---|---|---|
| high | cred | `http://127.0.0.1:5050/api/login` | 3 valid credentials in supplied list authenticate successfully (alice, bob, admin); admin grants role=admin in JWT |
| high | vuln_signal | `http://127.0.0.1:5050/admin/users` | Admin endpoint reachable with stolen admin creds (legal in this lab). In real engagement: confirms broken auth boundary  |
| med | auth | `http://127.0.0.1:5050/api/login` | JWT issued with HS256 + symmetric secret. Header.alg=HS256. Payload includes role claim — backend trusts this claim for  |

## Auth model
- Scheme: JWT bearer (HS256, symmetric secret)
- 401 responses include `WWW-Authenticate: Bearer`
- JWT payload contains `role` claim — backend trusts it for authorization
- Risk: if HS256 secret is weak or leaked, an attacker forges any role (incl. admin)
- Token lifetime: 1h (iat→exp delta)

## Credential test matrix

| user | attempts | success | account locked? |
|---|---|---|---|
| alice | 3 | ✓ | no signal |
| bob | 2 | ✓ | no signal |
| admin | 2 | ✓ | no signal |

(Raw passwords NOT stored — see `state/creds.log.jsonl` for `cred_id` + `pw_len` only.)

## Out-of-scope sightings
- `/admin/secret` declared in openapi.json but in scope.yaml deny list — recorded, not probed.
- openapi.servers points to `http://localhost:5050`, scope allows `127.0.0.1:5050` — same endpoint, different host string. Demo normalized; real engagements should add `localhost` to scope.allow or treat as OOS.

## Open questions / manual review
- Verify whether HS256 secret is rotated. Recommend RS256 + key rotation.
- `role` claim trusted from JWT — confirm no server-side role lookup; this is privilege-escalation surface if any user can self-issue tokens.
- `/admin/secret` should be tested in next run if scope is widened.
