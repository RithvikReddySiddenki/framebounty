"""EOA wallet authentication with server-owned, single-use challenges.

The signed message binds deployment origin and chain. Session tokens are random,
stored as hashes and expire; no signing keys are requested or retained. Contract
wallet (ERC-1271) authentication is not supported by this first implementation.
"""
import hashlib
import os
import re
import secrets
from datetime import UTC, datetime, timedelta

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import session
from .models import AuthSession, Nonce
from .networks import active_network

bearer = HTTPBearer(auto_error=False)


def wallet_address(value: str) -> str:
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", value) or int(value[2:], 16) == 0:
        raise ValueError("Invalid wallet address")
    return value.lower()


def challenge_message(wallet: str, nonce: str, expires: datetime) -> str:
    origin = os.getenv("AUTH_ORIGIN", "http://localhost:3000")
    chain = str(active_network().chain_id)
    return (f"FrameBounty wallet sign-in\nURI: {origin}\nChain ID: {chain}\n"
            f"Wallet: {wallet_address(wallet)}\nNonce: {nonce}\n"
            f"Expiration: {expires.isoformat()}\nThis signature does not authorize payments.")


def verify_signature(message: str, signature: str, wallet: str) -> bool:
    try:
        return Account.recover_message(encode_defunct(text=message), signature=signature).lower() == wallet_address(wallet)
    except (ValueError, TypeError):
        return False


def issue_challenge(db: Session, wallet: str) -> Nonce:
    nonce = secrets.token_hex(24)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    item = Nonce(id=nonce, wallet=wallet_address(wallet), message=challenge_message(wallet, nonce, expires), expires_at=expires, used=False)
    db.add(item)
    db.commit()
    return item


def sign_in(db: Session, nonce_id: str, signature: str) -> str:
    # Lock nonce consumption: simultaneous valid signatures can create only one session.
    nonce = db.scalar(select(Nonce).where(Nonce.id == nonce_id).with_for_update())
    if nonce is None or nonce.used or nonce.expires_at <= datetime.now(UTC):
        raise HTTPException(401, "Expired or consumed challenge")
    if (f"\nChain ID: {active_network().chain_id}\n" not in nonce.message
        or f"URI: {os.getenv('AUTH_ORIGIN', 'http://localhost:3000')}\n" not in nonce.message):
        raise HTTPException(401, "Challenge belongs to another network or origin")
    if not verify_signature(nonce.message, signature, nonce.wallet):
        raise HTTPException(401, "Signature does not match this challenge")
    nonce.used = True
    return create_session(db, nonce.wallet)


def create_session(db, wallet, circle_wallet_id=None):
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), wallet=wallet_address(wallet),
        expires_at=datetime.now(UTC) + timedelta(hours=8), chain_id=active_network().chain_id, circle_wallet_id=circle_wallet_id))
    db.commit()
    return token


def current_wallet(credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(session)) -> str:
    if credentials is None:
        raise HTTPException(401, "Connect and authenticate your wallet")
    item = db.get(AuthSession, hashlib.sha256(credentials.credentials.encode()).hexdigest())
    if item is None or item.expires_at <= datetime.now(UTC) or item.chain_id != active_network().chain_id:
        raise HTTPException(401, "Session expired")
    return item.wallet


def require_service_auth(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                         db: Session = Depends(session)):
    """Default-deny every product route, including future routes without a wallet arg.

    Only the exact sign-in endpoints and minimal liveness are public. Ownership
    remains enforced by each service; authentication alone grants no buyer powers.
    """
    public = {("POST", "/auth/challenge"), ("POST", "/auth/login"), ("GET", "/health")}
    public |= {("GET", "/auth/config"), *(("POST", "/auth/circle/" + name) for name in ("otp", "initialize", "wallets", "login"))}
    if (request.method, request.url.path) not in public:
        return current_wallet(credentials, db)


def revoke_session(credentials: HTTPAuthorizationCredentials, db: Session):
    item = db.get(AuthSession, hashlib.sha256(credentials.credentials.encode()).hexdigest())
    if item is not None:
        db.delete(item)
        db.commit()
