"""Real database + real decoder tests using generated non-human test patterns.

These prove orchestration and format handling, never towel-fold quality or Arc payout.
"""
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from framebounty.db import session
from framebounty.main import app
from framebounty.marketplace import prepare_confirmation, reserve
from framebounty.media import InvalidMedia, LocalStorage, inspect_video, media_executable
from framebounty.models import Job, Submission, VerificationJob
from framebounty.worker import claim, finish, run_once
from test_postgres import pg, seeded


@pytest.fixture
def video(tmp_path):
    executable = media_executable("ffmpeg")
    if not executable:
        pytest.skip("Real FFmpeg is required for generated-video integration tests")
    path = tmp_path / "synthetic-test-pattern.mp4"
    subprocess.run([executable, "-v", "error", "-nostdin", "-f", "lavfi", "-i",
        "testsrc2=size=320x240:rate=15", "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", "-y", str(path)], check=True, timeout=30, capture_output=True)
    return path.read_bytes()


def login(client, account):
    challenge = client.post("/auth/challenge", json={"wallet": account.address}).json()
    signature = Account.sign_message(encode_defunct(text=challenge["message"]), account.key).signature.hex()
    response = client.post("/auth/login", json={"nonce": challenge["nonce"], "signature": signature})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


@pytest.fixture
def flow(pg, tmp_path, monkeypatch):
    monkeypatch.setenv("APP_MODE", "fixture")
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "private-media"))
    buyer, contributor, stranger = Account.create(), Account.create(), Account.create()
    with Session(pg) as db:
        job, task = seeded(db, buyer=buyer.address.lower())
        confirmation = prepare_confirmation(db, contributor.address.lower(), task.id)
        item = reserve(db, contributor.address.lower(), confirmation.id, task.id, 1, 1_000_000, "video-flow-retry")
        job_id, reservation_id = job.id, item.id
    def request_session():
        with Session(pg) as db:
            yield db
    app.dependency_overrides[session] = request_session
    try:
        with TestClient(app) as client:
            yield client, login(client, buyer), login(client, contributor), login(client, stranger), job_id, reservation_id
    finally:
        app.dependency_overrides.clear()


def upload(client, auth, reservation, content, rights=True):
    return client.post(f"/reservations/{reservation}/video?rights_ack={str(rights).lower()}",
                       content=content, headers={**auth, "Content-Type": "video/mp4"})


def test_upload_decode_review_coverage_export_and_retry(pg, flow, video):
    client, buyer, contributor, stranger, job_id, reservation = flow
    assert upload(client, contributor, reservation, video, rights=False).status_code == 422
    assert upload(client, stranger, reservation, video).status_code == 404
    uploaded = upload(client, contributor, reservation, video)
    assert uploaded.status_code == 200, uploaded.text
    item = uploaded.json()
    submission_id = item["id"]
    assert item["state"] == "queued" and not item["payment_confirmed"]
    assert upload(client, contributor, reservation, video).json()["id"] == submission_id
    assert client.get(f"/submissions/{submission_id}/video", headers=stranger).status_code == 404
    assert client.get(f"/submissions/{submission_id}/video", headers=contributor).content == video
    assert run_once(pg)
    assert not run_once(pg)
    findings = client.get(f"/jobs/{job_id}/reviews", headers=buyer).json()["submissions"][0]
    assert findings["state"] == "needs_review"
    assert findings["findings"]["decoded"] is True
    assert len(findings["findings"]["frames"]) == 5
    assert all("key" not in frame for frame in findings["findings"]["frames"])
    assert findings["findings"]["assessment"]["task_completion"]["result"] == "uncertain"
    assert client.get(f"/submissions/{submission_id}/frames/0", headers=buyer).status_code == 200
    assert client.get(f"/submissions/{submission_id}/frames/0", headers=stranger).status_code == 404
    body = {"decision": "accept", "task_completed": False, "watched_full_video": True,
            "tags": ["large_towel", "dark_surface"], "reason": "Synthetic orchestration test attestation only"}
    assert client.post(f"/submissions/{submission_id}/review", headers=buyer, json=body).status_code == 422
    body["task_completed"] = True
    assert client.post(f"/submissions/{submission_id}/review", headers=contributor, json=body).status_code == 403
    first = client.post(f"/submissions/{submission_id}/review", headers=buyer, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["state"] == "fixture_accepted" and not first.json()["payment_confirmed"]
    assert client.post(f"/submissions/{submission_id}/review", headers=buyer, json=body).status_code == 200
    coverage = client.get(f"/jobs/{job_id}/coverage", headers=buyer).json()
    assert coverage["accepted_total"] == 1 and coverage["pending_total"] == 0
    assert coverage["accepted_categories"] == {"large_towel": 1, "dark_surface": 1}
    exported = client.get(f"/jobs/{job_id}/export", headers=buyer).json()
    assert len(exported["items"]) == 1 and exported["fixture"]
    assert client.get(f"/jobs/{job_id}/export", headers=stranger).status_code == 404
    import io, json, zipfile
    dataset = client.get(f"/jobs/{job_id}/dataset.zip", headers=buyer)
    assert dataset.status_code == 200
    with zipfile.ZipFile(io.BytesIO(dataset.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert len(manifest["items"]) == 1
        assert archive.read(manifest["items"][0]["path"]) == video
    assert client.get(f"/jobs/{job_id}/dataset.zip", headers=stranger).status_code == 404
    with Session(pg) as db:
        assert db.get(Job, job_id).paid_atomic == 1_000_000  # Explicit simulated ledger only.
        assert len(db.scalars(select(Submission)).all()) == 1


def test_corrupt_content_cannot_be_accepted(pg, flow):
    client, buyer, contributor, _, job_id, reservation = flow
    assert upload(client, contributor, reservation, b"fake video/mp4").status_code == 422
    response = upload(client, contributor, reservation, b"\x00\x00\x00\x18ftypisom" + b"corrupt" * 50)
    assert response.status_code == 200
    submission = response.json()["id"]
    assert run_once(pg)
    invalid = client.get(f"/jobs/{job_id}/reviews", headers=buyer).json()["submissions"][0]
    assert invalid["state"] == "invalid"
    body = {"decision": "accept", "task_completed": True, "watched_full_video": True,
            "tags": ["large_towel", "dark_surface"], "reason": "Cannot override invalid decoding"}
    assert client.post(f"/submissions/{submission}/review", headers=buyer, json=body).status_code == 422
    body.update(decision="reject", task_completed=False, watched_full_video=False, tags=[], reason="Corrupt video content")
    assert client.post(f"/submissions/{submission}/review", headers=buyer, json=body).status_code == 200
    with Session(pg) as db:
        assert db.get(Job, job_id).committed_atomic == 0


def test_worker_restart_fences_stale_completion_and_exhausted_lease(pg, flow, video):
    client, _, contributor, _, _, reservation = flow
    assert upload(client, contributor, reservation, video).status_code == 200
    with Session(pg) as db:
        first_id, first_token = claim(db)
        item = db.get(VerificationJob, first_id)
        item.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    with Session(pg) as db:
        second_id, second_token = claim(db)
        assert second_id == first_id and second_token != first_token
        assert not finish(db, first_id, first_token, {"decoded": True})
        assert finish(db, second_id, second_token, {"decoded": True, "frames": []})
    with Session(pg) as db:
        item = db.get(VerificationJob, first_id)
        item.state, item.attempts = "leased", 3
        item.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert claim(db) is None
        assert db.get(VerificationJob, first_id).state == "failed"


def test_real_metadata_and_full_decode_are_bounded(tmp_path, video):
    path = tmp_path / "test.video"
    path.write_bytes(video)
    assert inspect_video(path).duration_ms == 12000
    path.write_bytes(b"not a video")
    with pytest.raises(InvalidMedia):
        inspect_video(path)


def test_upload_bounds_and_submitted_obligation_survive_original_expiry(pg, flow, video):
    from framebounty.models import Reservation
    client, buyer, contributor, _, job_id, reservation = flow
    response = client.post(f"/reservations/{reservation}/video?rights_ack=true", content=b"small",
        headers={**contributor, "Content-Type": "video/mp4", "Content-Length": str(101 * 1024 * 1024)})
    assert response.status_code == 413
    response = client.post(f"/reservations/{reservation}/video?rights_ack=true", content=video,
        headers={**contributor, "Content-Type": "image/jpeg"})
    assert response.status_code == 415
    uploaded = upload(client, contributor, reservation, video)
    assert uploaded.status_code == 200
    submission_id = uploaded.json()["id"]
    with Session(pg) as db:
        item = db.get(Reservation, reservation)
        item.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    assert client.post(f"/reservations/{reservation}/release-expired", headers=contributor).status_code == 409
    assert run_once(pg)
    with Session(pg) as db:
        item = db.get(Submission, submission_id)
        item.review_deadline = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    body = {"decision": "accept", "task_completed": True, "watched_full_video": True,
            "tags": ["large_towel", "dark_surface"], "reason": "Late review must fail"}
    assert client.post(f"/submissions/{submission_id}/review", headers=buyer, json=body).status_code == 409
    assert client.post(f"/reservations/{reservation}/release-expired", headers=buyer).status_code == 200
    assert client.post(f"/reservations/{reservation}/release-expired", headers=buyer).status_code == 200
    with Session(pg) as db:
        assert db.get(Job, job_id).committed_atomic == 0


def test_stale_worker_cannot_resurrect_timed_out_review(pg, flow, video):
    client, buyer, contributor, _, _, reservation = flow
    uploaded = upload(client, contributor, reservation, video)
    submission_id = uploaded.json()["id"]
    with Session(pg) as db:
        work_id, token = claim(db)
        db.get(Submission, submission_id).review_deadline = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.post(f"/reservations/{reservation}/release-expired", headers=buyer).status_code == 200
    with Session(pg) as db:
        assert not finish(db, work_id, token, {"decoded": True})
        assert db.get(Submission, submission_id).state == "timed_out"
        assert db.get(VerificationJob, work_id).state == "cancelled"


def test_concurrent_workers_cannot_claim_same_submission(pg, flow, video):
    from concurrent.futures import ThreadPoolExecutor
    client, _, contributor, _, _, reservation = flow
    assert upload(client, contributor, reservation, video).status_code == 200
    def attempt():
        with Session(pg) as db:
            return claim(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sum(item is not None for item in results) == 1


def test_contributor_findings_do_not_reveal_other_submission_ids():
    from framebounty.submissions import submission_view
    item = Submission(id="own", reservation_id="reservation", job_id="job", state="needs_review",
        findings={"exact_duplicate_candidates": ["other-private-id"], "perceptual_duplicate_candidates": [], "frames": []},
        reviewed_tags=[], review_reason=None, review_deadline=datetime.now(UTC), rights_declaration="Test usage rights", rubric_hash="hash")
    public = submission_view(item)["findings"]
    assert "exact_duplicate_candidates" not in public and public["possible_duplicate_flagged"]
    assert submission_view(item, include_private_pairs=True)["findings"]["exact_duplicate_candidates"] == ["other-private-id"]
def test_transformed_clip_is_flagged_without_automatic_rejection(pg, flow, video, tmp_path):
    from framebounty.models import Task
    client, buyer, contributor, _, job_id, reservation = flow
    first = upload(client, contributor, reservation, video).json()["id"]
    assert run_once(pg)
    source, target = tmp_path / "source.mp4", tmp_path / "scaled.mp4"
    source.write_bytes(video)
    subprocess.run([media_executable("ffmpeg"), "-v", "error", "-nostdin", "-i", str(source),
        "-vf", "scale=640:480", "-c:v", "libx264", "-y", str(target)], check=True, timeout=30, capture_output=True)
    with Session(pg) as db:
        job, task = db.get(Job, job_id), db.get(Task, "towel-task")
        job.deposited_atomic, task.slots = 2_000_000, 2
        db.commit()
        wallet = db.get(Submission, first).wallet
        confirmation = prepare_confirmation(db, wallet, task.id)
        second_reservation = reserve(db, wallet, confirmation.id, task.id, 1, 1_000_000, "second-video-key").id
    second = upload(client, contributor, second_reservation, target.read_bytes()).json()["id"]
    assert run_once(pg)
    reviewed = client.get(f"/submissions/{second}", headers=buyer).json()
    assert reviewed["state"] == "needs_review"
    assert first in reviewed["findings"]["perceptual_duplicate_candidates"]
    assert reviewed["findings"]["exact_duplicate_candidates"] == []
    assert not reviewed["payment_confirmed"]
