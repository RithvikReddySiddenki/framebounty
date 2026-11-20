"""Real PostgreSQL chat intake, grounded facts, ownership and replay behavior."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from framebounty.chat import RANK_INSTRUCTION, ChatMessage, chat_turn, grounded_number, unlimited_time, stated_resources
from framebounty.marketplace import create_job
from framebounty.models import AgentSession, AgentTurn, Job, Reservation, Task
from framebounty.verification import GeminiFrames
from test_matching import cup_plan
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


def publish_cup(client, buyer):
    """The reported bug's post, created through the real buyer chat and simulated publish."""
    sid = start(client, buyer, "buyer")
    draft = send(client, buyer, sid, "I want 2 videos of a person pouring water into a cup under 2 USDC", "cup-buyer-post").json()
    assert draft["tool"] == "draft_plan", draft
    plan = draft["data"]["plan"]
    created = client.post("/jobs", headers=buyer, json={**plan, "budget_atomic": int(plan["budget_atomic"]),
        "reward_atomic": int(plan["reward_atomic"])}).json()
    assert client.post(f"/jobs/{created['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": created["plan_hash"], "confirmed": True}).status_code == 200
    return created["id"]


def test_contributor_with_a_cup_sees_the_cup_post_without_reserving(flow):
    client, buyer, actor, _, _, _ = flow
    job_id = publish_cup(client, buyer)
    sid = start(client, actor, "contributor")
    result = send(client, actor, sid, "I have a cup and no time limit", "cup-contributor").json()
    assert result["tool"] == "search_tasks", result
    assert [t["job_id"] for t in result["data"]["tasks"]] == [job_id]
    assert result["data"]["facts"] == {"equipment": ["cup"]} and result["data"]["ranked"] is False
    assert result["reply"] == "Here's 1 open task. Pick one to review its reward."
    # The fixture already has one reservation; chatting must not add another.
    assert len(client.get("/me/reservations", headers=actor).json()["reservations"]) == 1
    assert client.get("/chat-sessions?role=contributor", headers=actor).json()["sessions"][0]["id"] == sid


def test_find_work_asks_one_question_then_always_lists_open_tasks(flow):
    client, buyer, actor, _, _, _ = flow
    job_id = publish_cup(client, buyer)
    sid = start(client, actor, "contributor")
    first = send(client, actor, sid, "Find work", "find-work").json()
    assert first["tool"] == "clarify" and first["reply"].startswith("What do you have on hand?")
    assert first["data"]["missing"] == ["equipment"] and "tasks" not in first["data"]
    answer = send(client, actor, sid, "a mug", "find-work-answer").json()
    assert answer["tool"] == "search_tasks" and [t["job_id"] for t in answer["data"]["tasks"]] == [job_id]
    assert answer["data"]["facts"] == {"equipment": ["mug"]}
    more = send(client, actor, sid, "I also have a kettle", "find-work-more").json()
    assert more["data"]["facts"]["equipment"] == ["kettle", "mug"] and more["data"]["tasks"]
    nothing = send(client, actor, sid, "I have no equipment", "find-work-nothing").json()
    assert nothing["data"]["facts"]["equipment"] == [] and [t["job_id"] for t in nothing["data"]["tasks"]] == [job_id]


def test_show_me_whats_open_lists_without_asking(flow):
    client, buyer, actor, _, _, _ = flow
    job_id = publish_cup(client, buyer)
    sid = start(client, actor, "contributor")
    result = send(client, actor, sid, "Show me what's open.", "show-open").json()
    assert result["tool"] == "search_tasks" and [t["job_id"] for t in result["data"]["tasks"]] == [job_id]
    assert result["data"]["facts"] == {"equipment": []}


def test_empty_market_says_check_back_soon(flow):
    client, _, actor, _, _, _ = flow  # The seeded towel task is already fully reserved.
    sid = start(client, actor, "contributor")
    result = send(client, actor, sid, "I have a phone and a cat", "empty-market").json()
    assert result["tool"] == "search_tasks" and result["data"]["tasks"] == []
    assert result["reply"] == "There's no open funded work right now. Check back soon."


def chain_task(db, task_id, title, hours):
    job = create_job(db, "0x" + "4" * 40, cup_plan().model_copy(update={"title": title}))
    job.state, job.chain_id, job.deposited_atomic = "open", 5042002, 2_000_000
    db.add(Task(id=task_id, job_id=job.id, version=1, reward_atomic=1_000_000, slots=2, claimed=0, tags=["post_requirement"],
        equipment=["phone"], minutes=15, deadline=datetime.now(UTC) + timedelta(hours=hours), state="open"))


def routed(intake, ranking, seen):
    """Fake Gemini that answers intake and ranking calls separately; None means that call fails."""
    def respond(request):
        instruction = json.loads(request.content)["systemInstruction"]["parts"][0]["text"]
        payload = ranking if instruction == RANK_INSTRUCTION else intake
        seen.append("rank" if instruction == RANK_INSTRUCTION else "intake")
        if payload is None: return httpx.Response(503)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    return GeminiFrames("test-only", "verified-test-model", httpx.MockTransport(respond))


@pytest.fixture
def live_market(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true"); monkeypatch.setenv("ARC_CHAIN_ID", "5042002")
    wallet = "0x" + "5" * 40
    with Session(pg) as db:
        chain_task(db, "towel-live", "towel folding", 1)
        chain_task(db, "cup-live", "a person pouring water into a cup", 2)
        db.add(AgentSession(id="live-contributor", wallet=wallet, role="contributor", profile={"chat": True, "revision": 0}))
        db.commit()
    return wallet


def test_live_contributor_gets_gemini_ranked_tasks_with_reasons(pg, live_market):
    seen, text = [], "I have a mug and no time limit"
    model = routed({"equipment": ["mug"], "no_time_limit": True, "evidence": {"equipment": text, "no_time_limit": text}},
        {"tasks": [{"task_id": "cup-live", "reason": "A mug works as the cup."}, {"task_id": "towel-live", "reason": "You'd need a towel."}]}, seen)
    with Session(pg) as db:
        result = chat_turn(db, live_market, "live-contributor", ChatMessage(message=text, request_id="live-ranked"), model)
    assert seen == ["intake", "rank"]
    assert [t["task_id"] for t in result["data"]["tasks"]] == ["cup-live", "towel-live"]
    assert result["data"]["tasks"][0]["explanation"] == "A mug works as the cup." and result["data"]["ranked"] is True
    assert result["data"]["facts"] == {"equipment": ["mug"]}
    assert result["reply"] == "Here are 2 open tasks, best match first. Pick one to review its reward."


def test_live_contributor_still_sees_every_task_when_gemini_is_down(pg, live_market):
    seen = []
    with Session(pg) as db:
        result = chat_turn(db, live_market, "live-contributor", ChatMessage(message="I have a mug", request_id="live-down"), routed(None, None, seen))
    assert seen == ["intake", "rank"]
    assert result["data"]["facts"] == {"equipment": ["mug"]}  # The explicit "I have…" parser took over.
    assert [t["task_id"] for t in result["data"]["tasks"]] == ["towel-live", "cup-live"] and result["data"]["ranked"] is False
    assert result["reply"] == "Here are 2 open tasks. Pick one to review its reward."


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


def test_complete_buyer_request_uses_context_for_short_model_quotes(pg, monkeypatch):
    from framebounty.demo import example_plan
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")
    text = "I need 20 short videos of people folding towels, at least 5 with large towels and 5 on dark surfaces. Budget 20 USDC."
    wallet = "0x" + "3" * 40
    with Session(pg) as db:
        db.add(AgentSession(id="chat-short-quotes", wallet=wallet, role="buyer", profile={"chat": True, "revision": 0}))
        db.commit()
        model = adapter({"subject": "people folding towels", "media_type": "video", "count": 20, "budget_usdc": "20",
            "evidence": {"subject": "people folding towels", "media_type": "videos", "count": "20", "budget_usdc": "20"},
            "plan": example_plan().model_dump(mode="json")})
        result = chat_turn(db, wallet, "chat-short-quotes", ChatMessage(message=text, request_id="complete-short-quotes"), model)
        assert result["tool"] == "draft_plan" and result["data"]["missing"] == []
        assert result["data"]["plan"]["total"] == 20
        assert result["data"]["plan"]["budget_atomic"] == "20000000"
        assert db.scalar(select(func.count()).select_from(Job)) == 0


def test_old_bare_answer_cannot_be_reused_as_a_new_count(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")
    wallet = "0x" + "4" * 40
    with Session(pg) as db:
        db.add(AgentSession(id="chat-old-bare-answer", wallet=wallet, role="buyer", profile={"chat": True, "revision": 0}))
        db.commit()
        # A prior bare message lacks units. Its old contextual meaning is not
        # evidence for a later field merely because the current question changed.
        db.add(AgentTurn(id="old-bare-turn", session_id="chat-old-bare-answer", request_id="old-bare-request",
            message="20", tool="clarify", arguments={}, state="completed", result={}))
        row = db.get(AgentSession, "chat-old-bare-answer")
        row.profile = {"chat": True, "revision": 1, "facts": {"subject": "cats", "media_type": "image", "budget_usdc": "20"}, "awaiting": "count"}
        db.commit()
        result = chat_turn(db, wallet, row.id, ChatMessage(message="What information is missing?", request_id="old-answer-new-field"),
            adapter({"count": 20, "evidence": {"count": "20"}}))
        assert result["data"]["missing"] == ["count"]


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


@pytest.mark.parametrize("text,expected", [
    ("I have infinite amount of time.", True), ("I have unlimited time", True),
    ("No time limit", True), ("As long as it takes", True),
    ("I do not have unlimited time", False), ("I have 20 minutes", False),
])
def test_explicit_unlimited_time_is_not_an_invented_minute_count(text, expected):
    assert unlimited_time(text) is expected


def test_stated_resources_preserve_pets_and_respect_later_corrections():
    messages = ["I have a cat. What tasks are available?", "I have a phone to record and take pictures"]
    assert stated_resources(messages, ["phone"]) == ["cat", "phone"]
    assert stated_resources(messages + ["I have only 10 minutes"], ["phone"]) == ["cat", "phone"]
    assert stated_resources(messages + ["I only have a phone"], ["cat", "phone"]) == ["phone"]
    assert stated_resources(messages + ["I no longer have a cat"], ["cat", "phone"]) == ["phone"]


def test_cat_and_phone_contributor_sees_tasks_and_time_never_filters(pg, flow):
    client, buyer, actor, _, job_id, _ = flow
    plan = client.get(f"/jobs/{job_id}", headers=buyer).json()["plan"]
    created = client.post("/jobs", headers=buyer, json=plan).json()
    assert client.post(f"/jobs/{created['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": created["plan_hash"], "confirmed": True}).status_code == 200
    with Session(pg) as db:
        task = db.scalar(select(Task).where(Task.job_id == created["id"]))
        task.equipment, task.minutes = ["phone"], 2000  # A legacy listing that still names a phone and a long time.
        db.commit()
    sid = start(client, actor, "contributor")
    first = send(client, actor, sid, "I have a cat. What kinds of tasks are available for me.", "cat-search-first").json()
    assert first["tool"] == "search_tasks" and first["data"]["facts"] == {"equipment": ["cat"]}
    assert first["data"]["tasks"][0]["minutes"] == 2000
    second = send(client, actor, sid, "I have a phone to record and take pictures", "cat-search-phone").json()
    assert second["data"]["facts"]["equipment"] == ["cat", "phone"]
    limited = send(client, actor, sid, "I have only 10 minutes", "cat-search-limited").json()
    assert limited["data"]["facts"] == {"equipment": ["cat", "phone"]} and limited["data"]["tasks"]
    # A conversation saved by the old flow (waiting on a time answer) still lists work.
    with Session(pg) as db:
        scope = db.get(AgentSession, sid)
        scope.profile = {**scope.profile, "facts": {"equipment": ["phone"], "minutes": 10}, "awaiting": "minutes"}
        db.commit()
    again = send(client, actor, sid, "Find tasks", "cat-search-again").json()
    assert again["tool"] == "search_tasks" and again["data"]["tasks"]
    assert again["data"]["facts"] == {"equipment": ["cat", "phone"]}
