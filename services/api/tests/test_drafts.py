import pytest
from sqlalchemy.orm import Session
from framebounty.models import Job, TransactionIntent
from test_postgres import pg
from test_submission_flow import flow
from test_image_posts import image_plan

def test_only_buyer_can_remove_an_unfunded_draft_and_retry_is_safe(pg, flow):
    client, buyer, actor, _, funded, _ = flow
    draft = client.post("/jobs", headers=buyer, json=image_plan()).json()["id"]
    assert client.post(f"/jobs/{draft}/remove", headers=actor, json={}).status_code == 404
    assert client.post(f"/jobs/{funded}/remove", headers=buyer, json={}).status_code == 409
    for _ in range(2):
        assert client.post(f"/jobs/{draft}/remove", headers=buyer, json={}).json() == {"removed": True}
    assert draft not in {j["id"] for j in client.get("/me/jobs", headers=buyer).json()["jobs"]}
    with Session(pg) as db:
        assert db.get(Job, draft).archived
        assert not db.get(Job, funded).archived

@pytest.mark.parametrize("state", ["intent", "broadcast", "confirmed", "invalid"])
def test_pending_or_unreconciled_deposit_cannot_be_hidden_as_unfunded(pg, flow, state):
    client, buyer, _, _, _, _ = flow
    draft = client.post("/jobs", headers=buyer, json=image_plan()).json()["id"]
    with Session(pg) as db:
        job = db.get(Job, draft)
        db.add(TransactionIntent(id="a"*64, chain_id=5042002, kind="deposit", resource_id=draft,
            job_id=draft, sender=job.buyer, destination="0x"+"2"*40, call_data="0x12345678",
            expected_event={}, unsigned={}, state=state, projected=False, start_block=1))
        db.commit()
    response = client.post(f"/jobs/{draft}/remove", headers=buyer, json={})
    assert response.status_code == 409 and "deposit" in response.json()["detail"].lower()
    with Session(pg) as db: assert not db.get(Job, draft).archived

def test_awaiting_creation_can_be_removed_but_chain_funds_block_removal(pg, flow, monkeypatch):
    from framebounty import drafts
    from fastapi import HTTPException
    client, buyer, _, _, _, _ = flow
    draft = client.post("/jobs", headers=buyer, json=image_plan()).json()["id"]
    with Session(pg) as db:
        job = db.get(Job, draft)
        db.add(TransactionIntent(id="b"*64, chain_id=5042002, kind="create_protected", resource_id=draft,
            job_id=draft, sender=job.buyer, destination="0x"+"2"*40, call_data="0x12345678",
            expected_event={}, unsigned={}, state="intent", projected=False, start_block=1))
        db.commit()
    def funded(*_): raise HTTPException(409, "Escrow contains funds")
    monkeypatch.setattr(drafts, "check_chain_unfunded", funded)
    assert client.post(f"/jobs/{draft}/remove", headers=buyer, json={}).status_code == 409
    monkeypatch.setattr(drafts, "check_chain_unfunded", lambda *_: None)
    assert client.post(f"/jobs/{draft}/remove", headers=buyer, json={}).status_code == 200

def test_removal_serializes_against_new_deposit_intentions(pg, flow):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from types import SimpleNamespace
    from fastapi import HTTPException
    from framebounty.drafts import remove_draft
    from framebounty.chain_rpc import ChainFailure, escrow_call, resource_id
    from framebounty.transactions import Action, create_intent
    client, buyer, _, _, _, _ = flow
    jid = client.post("/jobs", headers=buyer, json=image_plan()).json()["id"]
    with Session(pg) as db: owner = db.get(Job, jid).buyer
    entered, release = Event(), Event()
    class RPC:
        config = SimpleNamespace(chain_id=5042002, escrow="0x"+"2"*40, token="0x3600000000000000000000000000000000000000")
        def check_contract(self): pass  # External RPC boundary only; real DB locks below.
        def rpc(self, method, params):
            assert method == "eth_blockNumber"
            entered.set(); assert release.wait(10)
            return "0x64"
    rpc = RPC()
    action = Action("deposit", jid, owner, rpc.config.escrow,
        escrow_call("deposit", [resource_id(jid), 20_000_000]),
        {"name": "Deposited", "fields": {"jobId": "0x"+resource_id(jid).hex(), "amount": 20_000_000}}, job_id=jid)
    def fund():
        with Session(pg) as db: return create_intent(db, rpc, action).state
    def remove():
        with Session(pg) as db:
            try: remove_draft(db, owner, jid)
            except HTTPException as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        funding = pool.submit(fund); assert entered.wait(10)
        removal = pool.submit(remove); release.set()
        assert funding.result(timeout=10) == "intent"
        assert removal.result(timeout=10) == 409
    with Session(pg) as db:
        assert not db.get(Job, jid).archived
        db.get(Job, jid).archived = True; db.commit()
        with pytest.raises(ChainFailure, match="Archived"):
            create_intent(db, rpc, action)

@pytest.mark.parametrize("challenge_state,expected", [("FAILED", 200), ("EXPIRED", 200), ("PENDING", 409), ("COMPLETE", 409)])
def test_circle_dead_deposit_approval_can_be_removed_but_live_approval_cannot(pg, flow, monkeypatch, challenge_state, expected):
    from framebounty import circle_wallets
    from framebounty.models import CircleChallenge
    client, buyer, _, _, _, _ = flow
    jid = client.post("/jobs", headers=buyer, json=image_plan()).json()["id"]
    wallet_id = "10000000-0000-4000-8000-000000000001"
    with Session(pg) as db:
        owner = db.get(Job, jid).buyer
        db.add(TransactionIntent(id="c"*64, chain_id=5042002, kind="deposit", resource_id=jid,
            job_id=jid, sender=owner, destination="0x"+"2"*40, call_data="0x12345678",
            expected_event={}, unsigned={}, state="intent", projected=False, start_block=1))
        db.flush()
        db.add(CircleChallenge(intent_id="c"*64, challenge_id="20000000-0000-4000-8000-000000000001", wallet_id=wallet_id))
        db.commit()
    class API:
        def owned_wallets(self, token):
            assert token == "test-private-token"
            return [{"id": wallet_id, "address": owner}]
        def call(self, method, path, token):
            assert method == "GET" and "/challenges/" in path
            return {"challenge": {"status": challenge_state, "correlationIds": []}}, {}
    monkeypatch.setattr(circle_wallets, "CircleAPI", API)
    response = client.post(f"/jobs/{jid}/remove", headers=buyer, json={"user_token": "test-private-token"})
    assert response.status_code == expected
    with Session(pg) as db: assert db.get(Job, jid).archived == (expected == 200)
