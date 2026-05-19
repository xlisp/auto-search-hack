# autohack report — examples/flask-api-project (v2 pipeline)

## Authorization

- type: own_system
- ref: examples/flask-api-project (local demo)
- expires: 2099-12-31

## Phase 0 — Static recon (recon.py)

- Source paths scanned: `examples/flask-api-project/`
- Routes extracted: 9
- URLs found in source: 6
- Doc files flagged for review: 2
- Secret hints (key names only, values not read): 0

### Routes (from source)

| Method | Path | Source |
|---|---|---|
| GET | `/health` | `examples/flask-api-project/app.py:63` |
| GET | `/openapi.json` | `examples/flask-api-project/app.py:68` |
| POST | `/api/login` | `examples/flask-api-project/app.py:86` |
| GET | `/api/me` | `examples/flask-api-project/app.py:96` |
| GET | `/api/users` | `examples/flask-api-project/app.py:102` |
| GET | `/api/posts` | `examples/flask-api-project/app.py:108` |
| GET | `/api/posts/<int:pid>` | `examples/flask-api-project/app.py:114` |
| GET | `/admin/users` | `examples/flask-api-project/app.py:123` |
| GET | `/admin/secret` | `examples/flask-api-project/app.py:132` |

## Network counts

- HTTP requests: 83
- Unique endpoints discovered: 8
- Findings: 30
- Response codes: {200: 23, 404: 46, 401: 13, 403: 1}
- Cred attempts: 14 | successes: 6
- Tokens captured: 3  (alice, bob, admin)

## Top findings (severity ≥ low)

| severity | type | target | evidence |
|---|---|---|---|
| high | cred | `http://127.0.0.1:5050/api/login` | 3 valid credentials in supplied list authenticate successfully (alice, bob, admin); admin grants role=admin in JWT |
| high | vuln_signal | `http://127.0.0.1:5050/admin/users` | Admin endpoint reachable with stolen admin creds (legal in this lab). In real engagement: confirms broken auth boundary  |
| high | auth_replay | `http://127.0.0.1:5050/admin/users` | label=admin_jwt JWT accessed sensitive endpoint http://127.0.0.1:5050/admin/users (200). Vertical privilege escalation c |
| med | auth | `http://127.0.0.1:5050/api/login` | JWT issued with HS256 + symmetric secret. Header.alg=HS256. Payload includes role claim — backend trusts this claim for  |

## Auth model

- Scheme: JWT bearer (HS256, symmetric secret)
- 401 responses include `WWW-Authenticate: Bearer`
- JWT payload contains `role` claim — backend trusts it for authorization
- Risk: HS256 secret leaked / weak → attacker forges any role (incl. admin)
- Token lifetime: 1h (iat→exp delta)

## Credential test matrix

| user | attempts | success | token captured |
|---|---|---|---|
| alice | 6 | ✓ | ✓ |
| bob | 4 | ✓ | ✓ |
| admin | 4 | ✓ | ✓ |

Raw passwords NOT stored — `state/creds.log.jsonl` records `cred_id` + `pw_len` only.

## JWT replay (broken-auth boundary check)

| label | target | code | severity | note |
|---|---|---|---|---|
| _ | `http://127.0.0.1:5050/admin/users` | _ | info | 403 — token authenticated but not authorized (proper boundary) |
| _ | `http://127.0.0.1:5050/api/me` | _ | info | label=alice_user_jwt JWT valid on http://127.0.0.1:5050/api/me (200) |
| _ | `http://127.0.0.1:5050/api/posts` | _ | info | label=alice_user_jwt JWT valid on http://127.0.0.1:5050/api/posts (200) |
| _ | `http://127.0.0.1:5050/api/posts/{id}` | _ | info | replay code=404 |
| _ | `http://127.0.0.1:5050/api/users` | _ | info | label=alice_user_jwt JWT valid on http://127.0.0.1:5050/api/users (200) |
| _ | `http://127.0.0.1:5050/health` | _ | info | label=alice_user_jwt JWT valid on http://127.0.0.1:5050/health (200) |
| _ | `http://127.0.0.1:5050/admin/users` | _ | high | label=admin_jwt JWT accessed sensitive endpoint http://127.0.0.1:5050/admin/users (200). V |
| _ | `http://127.0.0.1:5050/api/me` | _ | info | label=admin_jwt JWT valid on http://127.0.0.1:5050/api/me (200) |
| _ | `http://127.0.0.1:5050/api/posts` | _ | info | label=admin_jwt JWT valid on http://127.0.0.1:5050/api/posts (200) |
| _ | `http://127.0.0.1:5050/api/posts/{id}` | _ | info | replay code=404 |
| _ | `http://127.0.0.1:5050/api/users` | _ | info | label=admin_jwt JWT valid on http://127.0.0.1:5050/api/users (200) |
| _ | `http://127.0.0.1:5050/health` | _ | info | label=admin_jwt JWT valid on http://127.0.0.1:5050/health (200) |

**Result:** authorization boundary is intact — alice (user role) gets 403 on `/admin/users`, only admin's JWT yields 200.

## Out-of-scope sightings

- `/admin/secret` declared in openapi.json but in scope.yaml deny list — recorded, not probed.
- openapi.servers points to `http://localhost:5050`, scope allows `127.0.0.1:5050` — same endpoint, different host string.

## Open questions / manual review

- HS256 secret rotation? Recommend RS256 + key rotation.
- `role` claim trusted from JWT — confirm no server-side role lookup; this is privilege-escalation surface if any user can self-issue tokens.
- `/admin/secret` should be tested in next run if scope is widened.
