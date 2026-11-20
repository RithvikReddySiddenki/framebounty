"""Narrow Circle user-controlled wallet boundary; never trusts client identity.

SDK/user tokens remain short-lived and are never stored or logged. The server
checks ownership with Circle before issuing an app session or creating an exact
existing transaction-intent challenge. This is not a general signing proxy.
"""
import hashlib
import hmac
import os
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse, parse_qs
from uuid import UUID, uuid5, NAMESPACE_URL

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from sqlalchemy import select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from .auth import bearer, create_session, current_wallet, wallet_address
from .db import session
from .models import AuthSession, AuthRateBucket, CircleChallenge, TransactionIntent
from .networks import active_network, chain_enabled

router = APIRouter()


class AlreadyInitialized(Exception):
    pass


class CircleAPI:
    def __init__(self, transport=None):
        self.key = os.getenv("CIRCLE_API_KEY", "")
        if os.getenv("CIRCLE_ENABLED") != "true" or not self.key:
            raise HTTPException(503, "Circle sign-in is not configured yet")
        self.transport = transport

    def call(self, method, path, token=None, body=None, params=None):
        headers = {"Authorization": "Bearer " + self.key}
        if token: headers["X-User-Token"] = token
        try:
            with httpx.Client(base_url="https://api.circle.com", timeout=20, transport=self.transport,
                              follow_redirects=False) as client:
                response = client.request(method, path, headers=headers, json=body, params=params)
            if response.status_code in {401, 403}:
                raise HTTPException(401, "Circle session expired or access is unavailable; sign in again")
            if response.status_code == 429: raise HTTPException(429, "Too many Circle requests; wait before retrying")
            if response.status_code == 400 and response.json().get("code") == 155106:
                raise AlreadyInitialized()
            response.raise_for_status()
            payload = response.json().get("data")
            if not isinstance(payload, dict): raise ValueError()
            return payload, response.links
        except (httpx.HTTPError, ValueError, TypeError):
            # Raw Circle errors may contain private tokens/addresses. Do not
            # expose payloads or attach them to a logged exception chain.
            raise HTTPException(503, "Circle is unavailable; no payment or sign-in is assumed") from None

    def owned_wallets(self, token):
        user, _ = self.call("GET", "/v1/w3s/user", token)
        identity = user.get("user", user).get("id")
        if not isinstance(identity, str) or not identity: raise HTTPException(401, "Invalid Circle identity")
        network = active_network()
        wallets, cursor = [], None
        for _ in range(20):
            data, links = self.call("GET", "/v1/w3s/wallets", token,
                params={"blockchain": network.circle_chain, "pageSize": 50, **({"pageAfter": cursor} if cursor else {})})
            for wallet in data.get("wallets", []):
                if (wallet.get("blockchain") == network.circle_chain and wallet.get("accountType") == "EOA"
                    and wallet.get("state", "LIVE") == "LIVE" and wallet.get("userId", identity) == identity):
                    try:
                        wallets.append({"id": str(UUID(wallet["id"])), "address": wallet_address(wallet["address"]),
                            "blockchain": network.circle_chain})
                    except (KeyError, ValueError, TypeError): raise HTTPException(503, "Invalid Circle wallet metadata") from None
            next_link = links.get("next", {}).get("url")
            if not next_link: return wallets
            # Parse only the cursor; never forward credentials to a provider link.
            candidates = parse_qs(urlparse(next_link).query).get("pageAfter", [])
            if not candidates or candidates[0] == cursor: raise HTTPException(503, "Circle wallet pagination is unavailable")
            cursor = candidates[0]
        raise HTTPException(503, "Too many wallets to safely select an account")


def circle_api(): return CircleAPI()


class Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Device(Closed):
    device_id: UUID
    email: str | None = Field(default=None, min_length=3, max_length=254)


class UserToken(Closed):
    user_token: SecretStr = Field(min_length=20, max_length=8192)


class Initialize(UserToken):
    request_id: UUID


class CircleLogin(UserToken):
    wallet_id: UUID


def limit_login(db, api, identities):
    now = datetime.now(UTC)
    for namespace, identity, maximum in sorted(identities):
        key = hmac.new(api.key.encode(), (namespace + ":" + identity).encode(), "sha256").hexdigest()
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)})
        bucket = db.get(AuthRateBucket, key)
        if bucket is None:
            db.add(AuthRateBucket(id=key, started_at=now, attempts=1))
        else:
            if bucket.started_at <= now - timedelta(minutes=10): bucket.started_at, bucket.attempts = now, 0
            if bucket.attempts >= maximum: raise HTTPException(429, "Too many sign-in attempts; wait before requesting another code")
            bucket.attempts += 1
    db.commit()  # Failed provider calls still consume anti-abuse quota.


@router.get("/auth/config")
def configuration():
    network = active_network()
    return {"chain_id": network.chain_id, "network": network.name, "real_money": network.real_money,
        "rpc_url": network.rpc_url, "explorer": network.explorer,
        "circle_enabled": os.getenv("CIRCLE_ENABLED") == "true" and bool(os.getenv("CIRCLE_API_KEY")) and bool(os.getenv("CIRCLE_APP_ID"))
            and (os.getenv("CIRCLE_LOGIN_METHOD", "google") != "google" or bool(os.getenv("CIRCLE_GOOGLE_CLIENT_ID"))),
        "circle_app_id": os.getenv("CIRCLE_APP_ID", ""), "circle_login_method": os.getenv("CIRCLE_LOGIN_METHOD", "google"),
        "google_client_id": os.getenv("CIRCLE_GOOGLE_CLIENT_ID", "")}


@router.post("/auth/circle/otp")
def begin(body: Device, request: Request, db: Session = Depends(session), api=Depends(circle_api)):
    mode = os.getenv("CIRCLE_LOGIN_METHOD", "google")
    email = (body.email or "").strip().lower()
    if mode == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "Enter a valid email address")
    if mode not in {"email", "google"}: raise HTTPException(503, "Circle login method is not configured")
    identities = [("ip", request.client.host if request.client else "unknown", 30), ("device", str(body.device_id), 5)]
    if mode == "email": identities.append(("email", email, 5))
    limit_login(db, api, identities)
    data, _ = api.call("POST", "/v1/w3s/users/" + ("email" if mode == "email" else "social") + "/token",
        body={"idempotencyKey": str(uuid5(NAMESPACE_URL, "login:" + str(body.device_id) + ":" + str(datetime.now(UTC).timestamp()))),
              "deviceId": str(body.device_id), **({"email": email} if mode == "email" else {})})
    keys = ["deviceToken", "deviceEncryptionKey"] + (["otpToken"] if mode == "email" else [])
    if any(not isinstance(data.get(key), str) for key in keys): raise HTTPException(503, "Circle login response is incomplete")
    return {key: data[key] for key in keys}


@router.post("/auth/circle/wallets")
def wallets(body: UserToken, api=Depends(circle_api)):
    return {"wallets": api.owned_wallets(body.user_token.get_secret_value())}


@router.post("/auth/circle/initialize")
def initialize(body: Initialize, api=Depends(circle_api)):
    token = body.user_token.get_secret_value()
    existing = api.owned_wallets(token)
    if existing: return {"wallets": existing}
    creation = {"idempotencyKey": str(body.request_id), "accountType": "EOA", "blockchains": [active_network().circle_chain]}
    try: data, _ = api.call("POST", "/v1/w3s/user/initialize", token, body=creation)
    except AlreadyInitialized:
        # Returning users may already have a wallet on the other Arc network.
        # Never bind that wallet as though it held real USDC on this chain.
        creation["idempotencyKey"] = str(uuid5(NAMESPACE_URL, "additional-wallet:" + str(body.request_id)))
        data, _ = api.call("POST", "/v1/w3s/user/wallets", token, body={**creation,
            "metadata": [{"name": "FrameBounty " + active_network().name}]})
    try: return {"challenge_id": str(UUID(data["challengeId"]))}
    except (ValueError, KeyError): raise HTTPException(503, "Circle initialization is unverified") from None


@router.post("/auth/circle/login")
def login(body: CircleLogin, db: Session = Depends(session), api=Depends(circle_api)):
    owned = api.owned_wallets(body.user_token.get_secret_value())
    wallet = next((w for w in owned if w["id"] == str(body.wallet_id)), None)
    if wallet is None: raise HTTPException(401, "Wallet does not belong to this Circle session on the selected network")
    return {"wallet": wallet["address"], "token": create_session(db, wallet["address"], wallet["id"]), "expires_in_seconds": 28800}


def bound_session(db, credentials):
    item = db.get(AuthSession, hashlib.sha256(credentials.credentials.encode()).hexdigest())
    if not item or not item.circle_wallet_id: raise HTTPException(403, "Sign in through Circle to use this wallet")
    return item


class CircleTransaction(UserToken):
    intent_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    transaction: dict


@router.post("/circle/transactions")
def transaction(body: CircleTransaction, wallet: str = Depends(current_wallet),
                credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(session), api=Depends(circle_api)):
    if not chain_enabled(): raise HTTPException(503, "Chain transactions are disabled")
    session_row = bound_session(db, credentials)
    owned = api.owned_wallets(body.user_token.get_secret_value())
    if not any(w["id"] == session_row.circle_wallet_id and w["address"] == wallet for w in owned):
        raise HTTPException(403, "Circle user does not control the signed-in wallet")
    tx = body.transaction
    try:
        if set(tx) != {"from", "to", "data", "value", "chainId"} or wallet_address(tx["from"]) != wallet or int(tx["value"], 16) != 0:
            raise ValueError()
        if int(tx["chainId"], 16) != active_network().chain_id: raise ValueError()
        destination = wallet_address(tx["to"])
        if not re.fullmatch(r"0x(?:[0-9a-fA-F]{2}){4,10000}", tx["data"]): raise ValueError()
    except (ValueError, TypeError, KeyError): raise HTTPException(422, "Invalid wallet transaction") from None
    intent = db.get(TransactionIntent, body.intent_id)
    if (not intent or intent.sender != wallet or intent.destination != destination or intent.call_data != tx["data"].lower()
        or intent.chain_id != active_network().chain_id or intent.state not in {"intent", "broadcast", "confirmed"}):
        raise HTTPException(403, "Only an existing authorized marketplace intention may be signed")
    token = body.user_token.get_secret_value()
    if intent.tx_hash: return {"intent_id": intent.id, "tx_hash": intent.tx_hash}
    existing = db.get(CircleChallenge, intent.id)
    # A closed or timed-out PIN prompt leaves a FAILED/EXPIRED challenge. Reusing
    # it forever would block this action permanently, so only a challenge that is
    # provably dead (and produced no live Circle transaction) is replaced.
    if existing and not (existing.wallet_id == session_row.circle_wallet_id
                         and challenge_is_dead(api, token, existing.challenge_id, session_row.circle_wallet_id)):
        return {"intent_id": intent.id, "challenge_id": existing.challenge_id}
    # One deterministic key per attempt: concurrent retries of the same dead
    # challenge collapse to one new Circle challenge.
    attempt = intent.id if not existing else intent.id + ":" + existing.challenge_id
    data, _ = api.call("POST", "/v1/w3s/user/transactions/contractExecution", token, body={
        "idempotencyKey": str(uuid5(NAMESPACE_URL, "framebounty:" + attempt)), "walletId": session_row.circle_wallet_id,
        "contractAddress": intent.destination, "callData": intent.call_data, "refId": intent.id,
        "fee": {"type": "level", "config": {"feeLevel": "LOW"}}})
    try: challenge_id = str(UUID(data["challengeId"]))
    except (KeyError, ValueError): raise HTTPException(503, "Circle transaction is unverified; retry the same intention") from None
    if existing:
        # Compare-and-swap so a concurrent retry that already replaced the row wins.
        db.execute(update(CircleChallenge).where(CircleChallenge.intent_id == intent.id,
            CircleChallenge.challenge_id == existing.challenge_id).values(challenge_id=challenge_id))
    else:
        db.execute(insert(CircleChallenge).values(intent_id=intent.id, challenge_id=challenge_id,
            wallet_id=session_row.circle_wallet_id).on_conflict_do_nothing(index_elements=["intent_id"]))
    db.commit()
    db.expire_all()
    current = db.get(CircleChallenge, intent.id)
    return {"intent_id": intent.id, "challenge_id": current.challenge_id if current else challenge_id}


def challenge_is_dead(api, token: str, challenge_id: str, wallet_id: str) -> bool:
    """True only if the PIN challenge failed/expired and no transaction it created is still live."""
    data, _ = api.call("GET", "/v1/w3s/user/challenges/" + challenge_id, token)
    item = data.get("challenge", data)
    if item.get("status") not in {"FAILED", "EXPIRED"}:
        return False
    for tid in item.get("correlationIds", []):
        try: tid = str(UUID(tid))
        except ValueError: return False
        record, _ = api.call("GET", "/v1/w3s/transactions/" + tid, token)
        record = record.get("transaction", record)
        if record.get("walletId") != wallet_id or record.get("state") not in {"FAILED", "CANCELLED"}:
            return False
    return True


@router.post("/circle/transactions/{intent_id}/status")
def status(intent_id: str, body: UserToken, wallet: str = Depends(current_wallet),
           credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(session), api=Depends(circle_api)):
    auth = bound_session(db, credentials)
    challenge = db.get(CircleChallenge, intent_id)
    intent = db.get(TransactionIntent, intent_id)
    if not challenge or not intent or challenge.wallet_id != auth.circle_wallet_id or intent.sender != wallet:
        raise HTTPException(404, "Circle transaction not found")
    token = body.user_token.get_secret_value()
    if not any(w["id"] == auth.circle_wallet_id and w["address"] == wallet for w in api.owned_wallets(token)):
        raise HTTPException(403, "Circle wallet session changed")
    data, _ = api.call("GET", "/v1/w3s/user/challenges/" + challenge.challenge_id, token)
    item = data.get("challenge", data)
    result = {"challenge_status": item.get("status"), "state": "pending"}
    if item.get("status") in {"FAILED", "EXPIRED"}: return {**result, "state": "failed"}
    for tid in item.get("correlationIds", []):
        try: tid = str(UUID(tid))
        except ValueError: raise HTTPException(503, "Invalid Circle transaction reference") from None
        data, _ = api.call("GET", "/v1/w3s/transactions/" + tid, token)
        record = data.get("transaction", data)
        if record.get("walletId") != auth.circle_wallet_id or record.get("blockchain") != active_network().circle_chain:
            raise HTTPException(503, "Circle transaction belongs to another wallet or network")
        if record.get("state") in {"FAILED", "CANCELLED"}: return {**result, "state": "failed"}
        tx_hash = record.get("txHash")
        if isinstance(tx_hash, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", tx_hash):
            # This hash is only a candidate. Existing transaction attachment and
            # exact receipt matching still authorize all funding/payment records.
            return {**result, "state": "broadcast", "tx_hash": tx_hash}
    return result
