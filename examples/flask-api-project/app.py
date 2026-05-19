"""Demo Flask API with JWT auth — intentional target for autohack.

Endpoints:
    GET  /health              public
    GET  /openapi.json        public, full spec
    POST /api/login           public, returns JWT on valid creds
    GET  /api/me              JWT required
    GET  /api/users           JWT required
    GET  /api/posts           JWT required
    GET  /api/posts/<id>      JWT required
    GET  /admin/users         JWT + role=admin
    GET  /admin/secret        JWT + role=admin
"""
from __future__ import annotations
import datetime
from functools import wraps
from flask import Flask, request, jsonify
import jwt

app = Flask(__name__)
SECRET = "weak-demo-secret-do-not-use-in-prod"  # intentional: easy for autohack to flag

USERS = {
    "alice": {"password": "wonderland", "role": "user", "id": 1},
    "bob":   {"password": "builder42",  "role": "user", "id": 2},
    "admin": {"password": "admin",      "role": "admin", "id": 99},
}

POSTS = [
    {"id": 1, "author_id": 1, "title": "first post",  "body": "hello"},
    {"id": 2, "author_id": 2, "title": "second post", "body": "world"},
]


def make_token(username: str) -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": username,
        "role": USERS[username]["role"],
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, SECRET, algorithm="HS256")


def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        h = request.headers.get("Authorization", "")
        if not h.startswith("Bearer "):
            return jsonify({"error": "missing bearer token"}), 401, {
                "WWW-Authenticate": "Bearer"
            }
        try:
            payload = jwt.decode(h[7:], SECRET, algorithms=["HS256"])
        except jwt.PyJWTError as e:
            return jsonify({"error": f"invalid token: {e}"}), 401
        request.user = payload  # type: ignore[attr-defined]
        return f(*args, **kwargs)
    return wrapper


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/openapi.json")
def openapi():
    return {
        "openapi": "3.0.0",
        "info": {"title": "demo-flask-api", "version": "1.0.0"},
        "servers": [{"url": "http://localhost:5050"}],
        "paths": {
            "/api/login":       {"post": {"summary": "Login (returns JWT)"}},
            "/api/me":          {"get":  {"summary": "Current user from JWT"}},
            "/api/users":       {"get":  {"summary": "List users (auth)"}},
            "/api/posts":       {"get":  {"summary": "List posts (auth)"}},
            "/api/posts/{id}":  {"get":  {"summary": "Post by id (auth)"}},
            "/admin/users":     {"get":  {"summary": "Admin: list user accounts"}},
            "/admin/secret":    {"get":  {"summary": "Admin: a secret"}},
        },
    }


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    u, p = data.get("username"), data.get("password")
    user = USERS.get(u or "")
    if user and user["password"] == p:
        return {"token": make_token(u)}
    return {"error": "invalid credentials"}, 401


@app.get("/api/me")
@auth_required
def me():
    return {"user": request.user}  # type: ignore[attr-defined]


@app.get("/api/users")
@auth_required
def users():
    return {"users": [{"id": v["id"], "username": k} for k, v in USERS.items()]}


@app.get("/api/posts")
@auth_required
def posts():
    return {"posts": POSTS}


@app.get("/api/posts/<int:pid>")
@auth_required
def post_by_id(pid: int):
    for p in POSTS:
        if p["id"] == pid:
            return p
    return {"error": "not found"}, 404


@app.get("/admin/users")
@auth_required
def admin_users():
    if request.user.get("role") != "admin":  # type: ignore[attr-defined]
        return {"error": "forbidden"}, 403
    return {"users": [{"username": k, **{kk: vv for kk, vv in v.items() if kk != "password"}}
                      for k, v in USERS.items()]}


@app.get("/admin/secret")
@auth_required
def admin_secret():
    if request.user.get("role") != "admin":  # type: ignore[attr-defined]
        return {"error": "forbidden"}, 403
    return {"secret": "flag{autohack-demo-pwned}"}


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
