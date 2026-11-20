"""Contributor matching: every open task is listed, Gemini only orders it."""
import json

import httpx
import pytest
from sqlalchemy.orm import Session

from framebounty.chat import rank_tasks
from framebounty.domain import Plan
from framebounty.marketplace import create_job, open_tasks, search_tasks
from framebounty.models import Task
from framebounty.planning import publish_fixture
from framebounty.verification import GeminiFrames
from test_domain import draft
from test_postgres import pg, seeded

BUYER = "0x" + "3" * 40


def cup_plan() -> Plan:
    return Plan.model_validate({
        "requirements": [{"key": "post_requirement", "description": "Clearly show a person pouring water into a cup", "minimum": 2}],
        "version": 1, "min_seconds": 10, "max_seconds": 30, "review_hours": 72,
        "rights_declaration": "Fixture dataset only; contributors must have permission to share their media.",
        "media_type": "video", "title": "a person pouring water into a cup", "total": 2,
        "budget_atomic": 2_000_000, "reward_atomic": 1_000_000})


def publish(db, plan: Plan) -> Task:
    job = create_job(db, BUYER, plan)
    [task_id] = publish_fixture(db, BUYER, job.id, job.plan_hash)
    return db.get(Task, task_id)


def test_published_tasks_do_not_require_a_phone(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    with Session(pg) as db:
        assert publish(db, cup_plan()).equipment == []
        towel = publish(db, draft())
        assert "phone" not in towel.equipment and "towel" in towel.equipment


def test_open_tasks_lists_every_open_task_while_search_tasks_keeps_its_filter(pg, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    with Session(pg) as db:
        _, towel = seeded(db)  # Legacy row that still requires a phone and a towel.
        cup = publish(db, cup_plan())
        listed = [t["task_id"] for t in open_tasks(db)]
        assert listed == [towel.id, cup.id]  # Soonest deadline first.
        assert [t["task_id"] for t in search_tasks(db, {"cup"}, None)] == [cup.id]
        towel.claimed = towel.slots
        db.commit()
        assert [t["task_id"] for t in open_tasks(db)] == [cup.id]


def listing(task_id: str, title: str) -> dict:
    return {"task_id": task_id, "title": title, "media_type": "video", "explanation": "default line",
            "requirements": [{"key": "post_requirement", "description": "Clearly show " + title}]}


def gemini(payload=None, status=200, seen=None):
    def respond(request):
        if seen is not None: seen.append(request)
        if status != 200: return httpx.Response(status)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    return GeminiFrames("test-only", "verified-test-model", httpx.MockTransport(respond))


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")


TASKS = [listing("towel", "towel folding"), listing("cup", "a person pouring water into a cup"), listing("cat", "a cat climbing a tree")]


def test_rank_tasks_orders_validated_ids_and_never_drops_a_task(live):
    seen = []
    model = gemini({"tasks": [
        {"task_id": "cup", "reason": "You have a cup, and this task is pouring water into one. " + "x" * 300},
        {"task_id": "ghost", "reason": "Invented listing"},
        {"task_id": "cup", "reason": "Duplicate"},
        {"task_id": "towel", "reason": "  You didn't mention a towel.  "}]}, seen=seen)
    ranked, ok = rank_tasks(TASKS, ["I have a cup"], ["cup"], model)
    assert ok is True
    assert [t["task_id"] for t in ranked] == ["cup", "towel", "cat"]
    assert ranked[0]["explanation"].startswith("You have a cup") and len(ranked[0]["explanation"]) <= 140
    assert ranked[1]["explanation"] == "You didn't mention a towel."
    assert ranked[2]["explanation"] == "default line"
    assert seen[0].extensions["timeout"]["read"] == 15
    sent = json.loads(json.loads(seen[0].content)["contents"][0]["parts"][0]["text"])
    assert sent["contributor_messages"] == ["I have a cup"] and sent["items_on_hand"] == ["cup"]
    assert [t["task_id"] for t in sent["listings"]] == ["towel", "cup", "cat"]


@pytest.mark.parametrize("status", [500, 429])
def test_rank_tasks_falls_back_to_default_order_when_gemini_fails(live, status):
    ranked, ok = rank_tasks(TASKS, ["I have a cup"], ["cup"], gemini(status=status))
    assert ok is False and ranked == TASKS


def test_rank_tasks_falls_back_on_invalid_json(live):
    ranked, ok = rank_tasks(TASKS, ["I have a cup"], ["cup"], gemini({"unexpected": True}))
    assert ok is False and ranked == TASKS


def test_rank_tasks_skips_gemini_in_fixture_mode_or_without_consent(monkeypatch):
    seen = []
    monkeypatch.setenv("APP_MODE", "fixture"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "true")
    assert rank_tasks(TASKS, ["I have a cup"], ["cup"], gemini({"tasks": []}, seen=seen)) == (TASKS, False)
    monkeypatch.setenv("APP_MODE", "testnet"); monkeypatch.setenv("ALLOW_MODEL_TEXT", "false")
    assert rank_tasks(TASKS, ["I have a cup"], ["cup"], gemini({"tasks": []}, seen=seen)) == (TASKS, False)
    assert seen == []
    assert rank_tasks([], ["I have a cup"], ["cup"], gemini({"tasks": []}, seen=seen)) == ([], False)
