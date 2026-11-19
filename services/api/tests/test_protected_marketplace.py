"""Private originals, provider failure handling and fixed confirmation terms."""
from datetime import UTC, datetime, timedelta
from io import BytesIO
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from framebounty.models import Job, Reservation, Submission, VerificationJob
from framebounty.worker import run_once
from test_postgres import pg
from test_submission_flow import flow, video, upload
from test_automatic_verification import uploaded_ai


def test_unpaid_video_and_frame_aliases_cannot_leak_originals(pg, flow, video):
    client, buyer, actor, stranger, jid, rid = flow
    sid = upload(client, actor, rid, video).json()["id"]
    assert run_once(pg)
    for suffix in ["media", "video"]:
        assert client.get(f"/submissions/{sid}/{suffix}", headers=buyer).status_code == 403
        assert client.get(f"/submissions/{sid}/{suffix}", headers=actor).content == video
    preview = client.get(f"/submissions/{sid}/preview", headers=buyer)
    frame = client.get(f"/submissions/{sid}/frames/0", headers=buyer)
    assert preview.status_code == frame.status_code == 200 and preview.content == frame.content
    with Image.open(BytesIO(preview.content)) as image:
        assert max(image.size) <= 480 and not image.getexif()
    original_frame = client.get(f"/submissions/{sid}/frames/0", headers=actor)
    assert original_frame.content != frame.content
    assert client.get(f"/submissions/{sid}/preview", headers=stranger).status_code == 404
    assert client.get(f"/jobs/{jid}/export", headers=buyer).json()["items"] == []


def test_protected_provider_outage_retains_obligation_and_retries_after_cooldown(pg, flow, monkeypatch):
    client, buyer, actor, _, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "uncertain")
    jid, sid = uploaded_ai(client, buyer, actor)
    with Session(pg) as db:
        db.get(Job, jid).protection_version = 3; db.commit()
    for _ in range(3):
        with Session(pg) as db:
            work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == sid))
            work.lease_until = datetime.now(UTC) - timedelta(seconds=1); db.commit()
        assert run_once(pg)
    assert not run_once(pg)
    with Session(pg) as db:
        item = db.get(Submission, sid)
        assert item.state == "verification_pending"
        assert db.get(Job, jid).committed_atomic == 1_000_000
        work = db.scalar(select(VerificationJob).where(VerificationJob.submission_id == sid))
        work.available_at = datetime.now(UTC) - timedelta(seconds=1); db.commit()
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "pass")
    assert run_once(pg)
    with Session(pg) as db:
        assert db.get(Submission, sid).state == "verified"
        assert db.get(Job, jid).paid_atomic == 0


def test_confirmation_displays_and_preserves_exact_upload_deadline(pg, flow):
    from framebounty.marketplace import prepare_confirmation, reserve
    from framebounty.models import Task
    client, buyer, actor, _, jid, _ = flow
    with Session(pg) as db:
        task = db.scalar(select(Task).where(Task.job_id == jid))
        task.slots = 2; db.get(Job, jid).deposited_atomic = 2_000_000; db.commit()
        wallet = db.scalar(select(Reservation.wallet).where(Reservation.job_id == jid))
        confirmation = prepare_confirmation(db, wallet, task.id)
        shown = confirmation.reservation_expires_at
        result = reserve(db, wallet, confirmation.id, task.id, task.version, task.reward_atomic, "exact-deadline-confirmation")
        assert result.expires_at == shown


def test_fixture_trades_cannot_mint_chain_reputation(pg, flow, monkeypatch):
    client, buyer, actor, _, _, _ = flow
    jid, sid = uploaded_ai(client, buyer, actor)
    assert client.get(f"/submissions/{sid}/reputation", headers=actor).json()["supported"] is False
    assert client.post(f"/submissions/{sid}/reputation", headers=actor, json={"vote": 1}).status_code == 409
    assert client.post(f"/submissions/{sid}/reputation", headers=actor, json={"vote": 0}).status_code == 422
