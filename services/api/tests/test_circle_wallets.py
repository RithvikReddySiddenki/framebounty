"""Actual PostgreSQL sessions/rate limits; only Circle HTTP is a mock boundary."""
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4
import httpx
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.auth import current_wallet, issue_challenge, sign_in
from framebounty.circle_wallets import CircleAPI, CircleLogin, login, limit_login
from framebounty.models import AuthSession, AuthRateBucket
from framebounty.models import TransactionIntent, CircleChallenge
from framebounty.circle_wallets import CircleTransaction, UserToken, transaction, status
from test_postgres import pg

WALLET = "0x" + "1" * 40
WALLET_ID = "10000000-0000-4000-8000-000000000001"
USER_TOKEN = "private-user-token-never-log-this"


def test_initialized_user_can_create_a_wallet_on_the_selected_network(configured):
    from framebounty.circle_wallets import Initialize, initialize
    calls = []
    challenge = str(uuid4())
    def respond(request):
        if request.url.path.endswith("/user"):
            return httpx.Response(200, json={"data": {"id": "verified-user"}})
        if request.method == "GET":
            return httpx.Response(200, json={"data": {"wallets": [owned(blockchain="ARC")]}})
        import json
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        assert body["blockchains"] == ["ARC-TESTNET"] and body["accountType"] == "EOA"
        if request.url.path.endswith("/initialize"):
            return httpx.Response(400, json={"code": 155106})
        assert request.url.path.endswith("/user/wallets")
        return httpx.Response(200, json={"data": {"challengeId": challenge}})
    body = Initialize(user_token=USER_TOKEN, request_id=uuid4())
    assert initialize(body, CircleAPI(httpx.MockTransport(respond))) == {"challenge_id": challenge}
    assert len(calls) == 2 and calls[0][1]["idempotencyKey"] != calls[1][1]["idempotencyKey"]


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("CIRCLE_ENABLED", "true")
    monkeypatch.setenv("CIRCLE_API_KEY", "private-provider-key")
    monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    monkeypatch.setenv("APP_MODE", "testnet")


def api_for(wallets, requests=None):
    def respond(request):
        assert request.headers["X-User-Token"] == USER_TOKEN
        assert request.headers["Authorization"] == "Bearer private-provider-key"
        if requests is not None: requests.append(request)
        if request.url.path == "/v1/w3s/user": return httpx.Response(200, json={"data": {"id": "verified-user"}})
        assert request.url.path == "/v1/w3s/wallets"
        return httpx.Response(200, json={"data": {"wallets": wallets}})
    return CircleAPI(httpx.MockTransport(respond))


def owned(**updates):
    return {"id": WALLET_ID, "address": WALLET, "accountType": "EOA", "blockchain": "ARC-TESTNET", "userId": "verified-user", **updates}


def test_circle_login_uses_verified_wallet_ownership_and_network(pg, configured):
    with Session(pg) as db:
        result = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api_for([owned()]))
        assert result["wallet"] == WALLET and len(result["token"]) > 30
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=result["token"])
        assert current_wallet(credentials, db) == WALLET
        stored = db.get(AuthSession, hashlib.sha256(result["token"].encode()).hexdigest())
        assert stored.circle_wallet_id == WALLET_ID and stored.chain_id == 5042002


@pytest.mark.parametrize("wallet", [owned(blockchain="ARC"), owned(accountType="SCA"), owned(userId="another-user"), owned(state="FROZEN")])
def test_foreign_network_or_unowned_wallet_cannot_become_an_app_session(pg, configured, wallet):
    with Session(pg) as db:
        with pytest.raises(HTTPException) as error:
            login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api_for([wallet]))
        assert error.value.status_code == 401
        assert db.scalar(select(AuthSession)) is None


def test_an_invalid_circle_token_cannot_log_in(pg, configured):
    api = CircleAPI(httpx.MockTransport(lambda request: httpx.Response(401, json={"message": "private upstream body"})))
    with Session(pg) as db:
        with pytest.raises(HTTPException) as error: login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api)
        assert error.value.status_code == 401 and "private upstream" not in str(error.value.detail)
        assert db.scalar(select(AuthSession)) is None


def test_wallet_pagination_checks_next_page_without_following_foreign_hosts(configured):
    calls = []
    def respond(request):
        calls.append(str(request.url))
        if request.url.path.endswith("/user"): return httpx.Response(200, json={"data": {"id": "verified-user"}})
        if request.url.params.get("pageAfter"):
            return httpx.Response(200, json={"data": {"wallets": [owned()]}})
        return httpx.Response(200, json={"data": {"wallets": []}}, headers={
            "Link": '<https://foreign.invalid/steal?pageAfter=next-cursor>; rel="next"'})
    assert CircleAPI(httpx.MockTransport(respond)).owned_wallets(USER_TOKEN)[0]["id"] == WALLET_ID
    assert all(url.startswith("https://api.circle.com/") for url in calls)


def test_login_quota_is_persistent_and_does_not_store_raw_email(pg, configured):
    api = api_for([])
    with Session(pg) as db:
        for _ in range(5): limit_login(db, api, [("email", "user@example.com", 5)])
        with pytest.raises(HTTPException) as error: limit_login(db, api, [("email", "user@example.com", 5)])
        assert error.value.status_code == 429
        db.rollback()
        bucket = db.scalar(select(AuthRateBucket))
        assert bucket.attempts == 5 and "user@example.com" not in bucket.id
        bucket.started_at = datetime.now(UTC) - timedelta(minutes=11); db.commit()
        limit_login(db, api, [("email", "user@example.com", 5)])
        assert db.get(AuthRateBucket, bucket.id).attempts == 1


def test_existing_testnet_session_is_not_valid_on_mainnet(pg, configured, monkeypatch):
    with Session(pg) as db:
        result = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api_for([owned()]))
        monkeypatch.setenv("APP_MODE", "mainnet")
        monkeypatch.setenv("ARC_CHAIN_ID", "5042")
        monkeypatch.setenv("ALLOW_MAINNET_TRANSACTIONS", "true")
        with pytest.raises(HTTPException): current_wallet(HTTPAuthorizationCredentials(scheme="Bearer", credentials=result["token"]), db)


def payment_api(calls):
    def respond(request):
        import json
        assert request.headers["X-User-Token"] == USER_TOKEN
        if request.url.path == "/v1/w3s/user": return httpx.Response(200, json={"data": {"id": "verified-user"}})
        if request.url.path == "/v1/w3s/wallets": return httpx.Response(200, json={"data": {"wallets": [owned()]}})
        if request.url.path.endswith("/contractExecution"):
            calls.append(json.loads(request.content)); return httpx.Response(200, json={"data": {"challengeId": "20000000-0000-4000-8000-000000000001"}})
        if "/challenges/" in request.url.path:
            return httpx.Response(200, json={"data": {"challenge": {"status": "COMPLETE", "correlationIds": ["30000000-0000-4000-8000-000000000001"]}}})
        if "/transactions/" in request.url.path:
            return httpx.Response(200, json={"data": {"transaction": {"walletId": WALLET_ID, "blockchain": "ARC-TESTNET", "state": "SENT", "txHash": "0x" + "a" * 64}}})
        raise AssertionError("Unexpected provider operation")
    return CircleAPI(httpx.MockTransport(respond))


def pending_intent(db):
    item = TransactionIntent(id="a" * 64, chain_id=5042002, kind="token_approve", resource_id="b" * 32,
        sender=WALLET, destination="0x" + "2" * 40, call_data="0x12345678", expected_event={},
        unsigned={}, state="intent", projected=False, start_block=1)
    db.add(item); db.commit()
    return item, {"from": WALLET, "to": item.destination, "data": item.call_data, "value": "0x0", "chainId": hex(5042002)}


def test_circle_bridge_only_signs_exact_saved_intentions_and_recovers_same_challenge(pg, configured, monkeypatch):
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    calls = []; api = payment_api(calls)
    with Session(pg) as db:
        signed_in = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=signed_in["token"])
        item, tx = pending_intent(db)
        with pytest.raises(HTTPException):
            transaction(CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction={**tx, "data": "0x87654321"}), WALLET, credentials, db, api)
        assert not calls
        body = CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction=tx)
        first = transaction(body, WALLET, credentials, db, api)
        again = transaction(body, WALLET, credentials, db, api)
        assert first == again and len(calls) == 1
        assert calls[0]["callData"] == item.call_data and calls[0]["refId"] == item.id
        assert calls[0]["walletId"] == WALLET_ID
        candidate = status(item.id, UserToken(user_token=USER_TOKEN), WALLET, credentials, db, api)
        assert candidate["tx_hash"] == "0x" + "a" * 64
        # Circle's broadcast hash alone is never confirmed marketplace money.
        assert db.get(TransactionIntent, item.id).state == "intent"


def test_circle_bridge_rejects_external_wallet_sessions_and_network_or_value_changes(pg, configured, monkeypatch):
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    calls = []; api = payment_api(calls)
    with Session(pg) as db:
        signed_in = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=signed_in["token"])
        item, tx = pending_intent(db)
        for changed in [{**tx, "value": "0x1"}, {**tx, "chainId": hex(5042)}, {**tx, "from": "0x" + "3" * 40}]:
            with pytest.raises(HTTPException): transaction(CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction=changed), WALLET, credentials, db, api)
        assert not calls
        auth = db.get(AuthSession, hashlib.sha256(signed_in["token"].encode()).hexdigest())
        auth.circle_wallet_id = None; db.commit()
        with pytest.raises(HTTPException): transaction(CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction=tx), WALLET, credentials, db, api)
        assert not calls


def retrying_api(calls, challenge_status, transaction_state=None):
    """Circle mock where the first challenge is dead; each contractExecution returns a new challenge."""
    issued = []
    def respond(request):
        import json
        assert request.headers["X-User-Token"] == USER_TOKEN
        if request.url.path == "/v1/w3s/user": return httpx.Response(200, json={"data": {"id": "verified-user"}})
        if request.url.path == "/v1/w3s/wallets": return httpx.Response(200, json={"data": {"wallets": [owned()]}})
        if request.url.path.endswith("/contractExecution"):
            calls.append(json.loads(request.content))
            challenge = f"2000000{len(calls)}-0000-4000-8000-000000000001"
            issued.append(challenge)
            return httpx.Response(200, json={"data": {"challengeId": challenge}})
        if "/challenges/" in request.url.path:
            first = request.url.path.endswith(issued[0])
            correlation = ["30000000-0000-4000-8000-000000000001"] if transaction_state else []
            return httpx.Response(200, json={"data": {"challenge": {"status": challenge_status if first else "PENDING",
                                                                    "correlationIds": correlation}}})
        if "/transactions/" in request.url.path:
            return httpx.Response(200, json={"data": {"transaction": {"walletId": WALLET_ID, "blockchain": "ARC-TESTNET", "state": transaction_state}}})
        raise AssertionError("Unexpected provider operation")
    return CircleAPI(httpx.MockTransport(respond))


@pytest.mark.parametrize("challenge_status", ["FAILED", "EXPIRED"])
def test_closed_or_expired_circle_prompt_gets_a_fresh_challenge_on_retry(pg, configured, monkeypatch, challenge_status):
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    calls = []; api = retrying_api(calls, challenge_status)
    with Session(pg) as db:
        signed_in = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=signed_in["token"])
        item, tx = pending_intent(db)
        body = CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction=tx)
        first = transaction(body, WALLET, credentials, db, api)
        retry = transaction(body, WALLET, credentials, db, api)
        assert retry["challenge_id"] != first["challenge_id"] and len(calls) == 2
        # Each attempt uses its own idempotency key and still signs only the saved intention.
        assert calls[0]["idempotencyKey"] != calls[1]["idempotencyKey"]
        assert calls[1]["callData"] == item.call_data and calls[1]["refId"] == item.id
        assert db.get(CircleChallenge, item.id).challenge_id == retry["challenge_id"]
        # The new challenge is live, so a further retry reuses it.
        assert transaction(body, WALLET, credentials, db, api) == retry and len(calls) == 2


def test_dead_prompt_with_a_live_circle_transaction_is_not_replaced(pg, configured, monkeypatch):
    monkeypatch.setenv("ALLOW_CHAIN_TRANSACTIONS", "true")
    calls = []; api = retrying_api(calls, "FAILED", transaction_state="SENT")
    with Session(pg) as db:
        signed_in = login(CircleLogin(user_token=USER_TOKEN, wallet_id=WALLET_ID), db, api)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=signed_in["token"])
        item, tx = pending_intent(db)
        body = CircleTransaction(user_token=USER_TOKEN, intent_id=item.id, transaction=tx)
        first = transaction(body, WALLET, credentials, db, api)
        assert transaction(body, WALLET, credentials, db, api) == first and len(calls) == 1
