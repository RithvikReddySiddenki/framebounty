"""Real PostgreSQL chat intake, grounded facts, ownership and replay behavior."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from framebounty.chat import ChatMessage, chat_turn, grounded_number
from framebounty.models import AgentSession, AgentTurn, Job, Reservation
from framebounty.verification import GeminiFrames
from test_postgres import pg
from test_submission_flow import flow


def start(client, headers, role):
    response = client.post("/chat-sessions", headers=headers, json={"role": role})
    assert response.status_code == 200
    return response.json()["id"]


def send(client, headers, sid, message, request_id):
    return client.post(f"/chat-sessions/{sid}/messages", headers=headers, json={"message": message, "request_id": request_id})


def test_buyer_clarifies_count_then_budget_without_creating_or_publishing(flow):
    client, buyer, _, stranger, _, _ = flow
    sid = start(client, buyer, "buyer")
    response = send(client, buyer, sid, "I want images of a cat climbing a tree", "chat-buyer-first").json()
    assert response["tool"] == "clarify" and "count" in response["data"]["missing"]
    assert "plan" not in response["data"]
    second = send(client, buyer, sid, "20", "chat-buyer-count").json()
    assert second["data"]["facts"]["count"] == 20 and second["data"]["missing"] == ["budget_usdc"]
    final = send(client, buyer, sid, "20 USDC", "chat-buyer-budget").json()
    assert final["tool"] == "draft_plan"
    assert final["data"]["plan"]["media_type"] == "image" and final["data"]["plan"]["total"] == 20
    assert final["data"]["plan"]["budget_atomic"] == "20000000"
    assert len(client.get("/me/jobs", headers=buyer).json()["jobs"]) == 1  # Only preexisting fixture.
    assert send(client, stranger, sid, "Publish and pay me", "other-wallet-chat").status_code == 404
    assert client.get("/chat-sessions?role=contributor", headers=buyer).json()["sessions"] == []


def test_contributor_clarifies_time_and_searches_real_tasks_without_reserving(flow):
    client, buyer, actor, _, job_id, _ = flow
    plan = client.get(f"/jobs/{job_id}", headers=buyer).json()["plan"]
    created = client.post("/jobs", headers=buyer, json=plan).json()
    assert client.post(f"/jobs/{created['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": created["plan_hash"], "confirmed": True}).status_code == 200
    sid = start(client, actor, "contributor")
    first = send(client, actor, sid, "I have a phone, a towel and a dark table", "chat-equipment-first").json()
    assert first["data"]["missing"] == ["minutes"] and "time" in first["reply"]
    result = send(client, actor, sid, "20 minutes", "chat-time-answer").json()
    assert result["tool"] == "search_tasks" and result["data"]["tasks"]
    assert result["data"]["facts"] == {"equipment": ["dark_table", "phone", "towel"], "minutes": 20}
    # The fixture already has one reservation; chatting must not add another.
    assert len(client.get("/me/reservations", headers=actor).json()["reservations"]) == 1
    assert client.get("/chat-sessions?role=contributor", headers=actor).json()["sessions"][0]["id"] == sid
    corrected = send(client, actor, sid, "I have no equipment", "chat-profile-correction").json()
    assert corrected["data"]["facts"]["equipment"] == [] and corrected["data"]["tasks"] == []


def test_chat_replay_and_request_conflicts_preserve_history(pg, flow):
    client, buyer, _, _, _, _ = flow
    sid = start(client, buyer, "buyer")
    first = send(client, buyer, sid, "I want images of cats under 20 USDC", "chat-replay-request")
    assert first.json()["data"]["missing"] == ["count"]
    assert send(client, buyer, sid, "I want images of cats under 20 USDC", "chat-replay-request").json() == first.json()
    assert send(client, buyer, sid, "20", "chat-replay-request").status_code == 409
    with Session(pg) as db:
        assert db.scalar(select(func.count()).select_from(AgentTurn).where(AgentTurn.session_id == sid)) == 1


def adapter(payload, barrier=None):
    def respond(request):
        if barrier: barrier.wait(timeout=10)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    return GeminiFrames("test-only", "verified-test-model", httpx.MockTransport(respond))


def test_live_intake_cannot_invent_count_from_budget(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")
    text = "I want images of cats under 20 USDC"
    wallet = "0x" + "1" * 40
    with Session(pg) as db:
        db.add(AgentSession(id="chat-grounding", wallet=wallet, role="buyer", profile={"chat": True, "revision": 0}))
        db.commit()
        model = adapter({"subject": "cats", "media_type": "image", "count": 20, "budget_usdc": "20",
            "evidence": {field: text for field in ["subject", "media_type", "count", "budget_usdc"]}})
        result = chat_turn(db, wallet, "chat-grounding", ChatMessage(message=text, request_id="chat-no-invented-count"), model)
        assert result["data"]["missing"] == ["count"] and "plan" not in result["data"]
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_concurrent_chat_turns_do_not_overwrite_each_others_facts(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")
    wallet, text = "0x" + "2" * 40, "I want images of cats"
    with Session(pg) as db:
        db.add(AgentSession(id="chat-concurrent", wallet=wallet, role="buyer", profile={"chat": True, "revision": 0}))
        db.commit()
    barrier = Barrier(2)
    def run(index):
        with Session(pg) as db:
            try:
                chat_turn(db, wallet, "chat-concurrent", ChatMessage(message=text, request_id=f"chat-concurrent-{index}"),
                    adapter({"subject": "cats", "media_type": "image", "evidence": {"subject": text, "media_type": text}}, barrier))
                return 200
            except HTTPException as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, [1, 2])) == [200, 409]


@pytest.mark.parametrize("field,value,quote,awaiting,valid", [
    ("count", 20, "20 USDC for images of cats", None, False),
    ("count", 20, "twenty images of cats", None, True),
    ("count", 5, "5", "count", True),
    ("budget_usdc", "20.00", "under 20 USDC", None, True),
    ("budget_usdc", "20", "20 photos", None, False),
    ("minutes", 30, "half an hour", None, True),
    ("minutes", 60, "an hour", None, True),
    ("minutes", 20, "20 USDC", None, False),
])
def test_numeric_facts_are_grounded_in_the_correct_user_statement(field, value, quote, awaiting, valid):
    assert grounded_number(field, value, quote, awaiting) is valid
