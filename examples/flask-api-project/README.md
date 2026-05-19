# examples/flask-api-project — JWT demo target

A small Flask service used as a legal own-system target for `autohack`.

## Run the target

```bash
pip install -r requirements.txt
python app.py
# serves on http://127.0.0.1:5050
```

## Endpoints

| Method | Path                | Auth                  |
|--------|---------------------|-----------------------|
| GET    | `/health`           | public                |
| GET    | `/openapi.json`     | public                |
| POST   | `/api/login`        | public                |
| GET    | `/api/me`           | JWT                   |
| GET    | `/api/users`        | JWT                   |
| GET    | `/api/posts`        | JWT                   |
| GET    | `/api/posts/<id>`   | JWT                   |
| GET    | `/admin/users`      | JWT + role=admin      |
| GET    | `/admin/secret`     | JWT + role=admin      |

## Valid credentials (built-in)

- `alice:wonderland`
- `bob:builder42`
- `admin:admin`

## Run autohack against it

From repo root:

```bash
cp examples/flask-api-project/scope.yaml ./scope.yaml
cp examples/flask-api-project/creds.txt  ./state/creds.txt
# in another terminal: python examples/flask-api-project/app.py
# then in Claude Code: "look at program.md and start an autohack run"
```
