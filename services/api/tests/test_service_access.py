"""Default-deny routes and real PostgreSQL signed-session access/revocation."""
import hashlib
import re
from datetime import UTC, datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from framebounty.db import session
from framebounty.main import app
from framebounty.models import AuthSession
from test_postgres import pg


def test_every_product_route_denies_anonymous_access_before_service_execution():
    public = {("GET", "/health"), ("POST", "/auth/challenge"), ("POST", "/auth/login")}
    with TestClient(app) as client:
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue
            path = re.sub(r"\{[^}]+\}", "a" * 32, route.path)
            for method in route.methods:
                if (method, route.path) in public:
                    continue
                response = client.request(method, path, **({"json": {}} if method == "POST" else {}))
                assert response.status_code == 401, f"Anonymous service exposed: {method} {route.path}"
        for path in ("/docs", "/redoc", "/openapi.json"):
            assert client.get(path).status_code == 404


def login(client):
    account = Account.create()
    challenge = client.post("/auth/challenge", json={"wallet": account.address})
    assert challenge.status_code == 200
    body = challenge.json()
    signature = Account.sign_message(encode_defunct(text=body["message"]), account.key).signature.hex()
    response = client.post("/auth/login", json={"nonce": body["nonce"], "signature": signature})
    assert response.status_code == 200
    return response.json()["token"]


def test_signed_access_logout_expiry_and_invalid_tokens(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    def request_session():
        with Session(pg) as db:
            yield db
    app.dependency_overrides[session] = request_session
    try:
        with TestClient(app) as client:
            token = login(client)
            other = login(client)
            headers = {"Authorization": "Bearer " + token}
            assert client.get("/tasks", headers=headers).status_code == 200
            assert client.get("/me/overview", headers=headers).json() == {
                "collections": 0, "open_collections": 0, "awaiting_review": 0, "fixture": True}
            # Preserve the original HTTP plan-validation coverage behind real auth.
            assert client.post("/plans/validate", headers=headers, json={"budget_atomic": -1}).status_code == 422
            assert client.get("/me/status", headers=headers).json()["mode"] == "fixture"
            assert client.post("/auth/logout", headers=headers, json={}).json() == {"signed_out": True}
            assert client.get("/tasks", headers=headers).status_code == 401
            assert client.get("/me/overview", headers=headers).status_code == 401
            assert client.get("/tasks", headers={"Authorization": "Bearer " + other}).status_code == 200
            with Session(pg) as db:
                saved = db.get(AuthSession, hashlib.sha256(other.encode()).hexdigest())
                saved.expires_at = datetime.now(UTC) - timedelta(seconds=1)
                db.commit()
            assert client.get("/tasks", headers={"Authorization": "Bearer " + other}).status_code == 401
            assert client.get("/tasks", headers={"Authorization": "Bearer fabricated-token"}).status_code == 401
    finally:
        app.dependency_overrides.clear()
