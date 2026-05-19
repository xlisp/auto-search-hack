# wordlists/

Small, deliberately conservative wordlists bundled with autohack.

| File                  | Used by                | Auth gate                              |
|-----------------------|------------------------|----------------------------------------|
| `api-paths.txt`       | `discover.py` default  | always allowed                         |
| `common-usernames.txt`| `creds.py` combo mode  | `own_system` / `ctf` only (auto-gated) |
| `common-passwords.txt`| `creds.py` common mode | `own_system` / `ctf` only (auto-gated) |

These are **smoke-test sized**, not engagement-grade. For real bug bounty / pentest
work, provide your own engagement-appropriate lists via `--wordlist` / `--user-list`
/ `--pass-list` — that decision belongs to your SOW, not this repo.

Gates are enforced in `tools/discover.py` and `tools/creds.py`:
- `bug_bounty` / `client_pentest` authorization types **refuse** the bundled
  username/password lists unless `scope.yaml` explicitly sets
  `aggressive_credentials: true` (your engagement, your call).
- `discover.py` will still use `api-paths.txt` since endpoint enumeration is
  read-only, but you can override with `--wordlist` to match the engagement scope.
