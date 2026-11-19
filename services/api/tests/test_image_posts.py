"""Real PostgreSQL, private bytes, Pillow decode and export; synthetic images only."""
import io
import json
import zipfile

import httpx
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from framebounty.domain import Plan
from framebounty.media import LocalStorage, InvalidMedia, inspect_image
from framebounty.models import Job
from framebounty.verification import GeminiFrames, ProviderFailure
from framebounty.worker import run_once
from test_postgres import pg
from test_submission_flow import flow, video


def image_bytes(fmt="PNG", size=(320, 240)):
    stream = io.BytesIO()
    Image.new("RGB", size, "green").save(stream, fmt)
    return stream.getvalue()


def image_plan():
    return dict(verification_policy="human", media_type="image", version=1, title="Cat climbing a tree", total=20,
        budget_atomic=20_000_000, reward_atomic=1_000_000, min_seconds=10, max_seconds=10,
        review_hours=72, rights_declaration="Synthetic test images only; no real animal or capture claim.",
        requirements=[dict(key="cat_climbing_tree", description="A cat visibly climbing a tree", minimum=20)])


def reserve_image(client, buyer, actor):
    created = client.post("/jobs", headers=buyer, json=image_plan())
    assert created.status_code == 200, created.text
    job = created.json()
    listing = next(p for p in client.get("/me/jobs", headers=buyer).json()["jobs"] if p["id"] == job["id"])
    assert listing["publication_status"] == "draft" and listing["media_type"] == "image"
    assert client.post(f"/jobs/{job['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": job["plan_hash"], "confirmed": True}).status_code == 200
    listing = next(p for p in client.get("/me/jobs", headers=buyer).json()["jobs"] if p["id"] == job["id"])
    assert listing["publication_status"] == "open" and listing["open_slots"] == 2
    task = next(t for t in client.get("/tasks?equipment=phone", headers=actor).json()["tasks"] if t["job_id"] == job["id"])
    assert task["media_type"] == "image" and task["equipment"] == ["phone"]
    confirmation = client.post(f"/tasks/{task['task_id']}/confirmation", headers=actor).json()
    reserved = client.post("/reservations", headers=actor, json={
        "confirmation_id": confirmation["confirmation_id"], "task_id": task["task_id"], "version": task["version"],
        "reward_atomic": task["reward_atomic"], "confirmed": True, "idempotency_key": "image-reservation-test"})
    assert reserved.status_code == 200
    return job["id"], reserved.json()["id"]


@pytest.mark.parametrize("fmt,mime,extension", [("PNG", "image/png", "png"), ("JPEG", "image/jpeg", "jpg")])
def test_private_image_upload_verification_review_export(pg, flow, fmt, mime, extension):
    client, buyer, actor, stranger, _, _ = flow
    job_id, reservation = reserve_image(client, buyer, actor)
    data = image_bytes(fmt)
    endpoint = f"/reservations/{reservation}/image?rights_ack=true&model_ack=true"
    assert client.post(endpoint, headers={**stranger, "Content-Type": mime}, content=data).status_code == 404
    assert client.post(endpoint.replace("rights_ack=true", "rights_ack=false"), headers={**actor, "Content-Type": mime}, content=data).status_code == 422
    assert client.post(endpoint.replace("/image?", "/video?"), headers={**actor, "Content-Type": mime}, content=data).status_code == 415
    result = client.post(endpoint, headers={**actor, "Content-Type": mime}, content=data)
    assert result.status_code == 200, result.text
    submission = result.json()["id"]
    assert result.json()["media_type"] == "image"
    assert client.post(endpoint, headers={**actor, "Content-Type": mime}, content=data).json()["id"] == submission
    assert client.get(f"/submissions/{submission}/media", headers=stranger).status_code == 404
    assert client.get(f"/submissions/{submission}/media", headers=buyer).status_code == 409
    assert client.get(f"/submissions/{submission}/media", headers=actor).content == data
    assert run_once(pg)
    preview = client.get(f"/submissions/{submission}/media", headers=buyer)
    assert preview.status_code == 200 and preview.content != data
    assert preview.headers["content-type"] == "image/jpeg"
    assert client.get(f"/submissions/{submission}/frames/0", headers=buyer).content == preview.content
    verified = client.get(f"/submissions/{submission}", headers=actor).json()
    assert verified["state"] == "needs_review" and verified["findings"]["decoded"]
    assert set(verified["findings"]["assessment"]) == {"task_completion", "visibility", "cat_climbing_tree"}
    assert verified["findings"]["assessment"]["cat_climbing_tree"]["result"] == "uncertain"
    body = dict(decision="accept", task_completed=True, watched_full_video=True, tags=["cat_climbing_tree"], reason="Synthetic workflow validation only")
    assert client.post(f"/submissions/{submission}/review", headers=actor, json=body).status_code == 403
    assert client.post(f"/submissions/{submission}/review", headers=buyer, json=body).json()["state"] == "fixture_accepted"
    assert client.get(f"/submissions/{submission}/media", headers=buyer).content == data
    exported = client.get(f"/jobs/{job_id}/dataset.zip", headers=buyer)
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        path = manifest["items"][0]["path"]
        assert path.startswith("images/") and path.endswith("." + extension)
        assert archive.read(path) == data and manifest["plan"]["media_type"] == "image"


def test_corrupt_and_mislabeled_images_never_become_accepted(pg, flow):
    client, buyer, actor, _, _, _ = flow
    _, reservation = reserve_image(client, buyer, actor)
    endpoint = f"/reservations/{reservation}/image?rights_ack=true"
    assert client.post(endpoint, headers={**actor, "Content-Type": "image/png"}, content=b"not an image").status_code == 422
    uploaded = client.post(endpoint, headers={**actor, "Content-Type": "image/jpeg"}, content=image_bytes()).json()
    assert run_once(pg)
    result = client.get(f"/submissions/{uploaded['id']}", headers=buyer).json()
    assert result["state"] == "invalid" and "declared type" in result["findings"]["processing_error"]


def test_image_size_limit_and_claimed_out_post_status(pg, flow):
    client, buyer, actor, stranger, _, _ = flow
    job_id, reservation = reserve_image(client, buyer, actor)
    response = client.post(f"/reservations/{reservation}/media?rights_ack=true", content=b"short",
        headers={**actor, "Content-Type": "image/png", "Content-Length": str(21 * 1024 * 1024)})
    assert response.status_code == 413
    task = next(t for t in client.get("/tasks?equipment=phone", headers=actor).json()["tasks"] if t["job_id"] == job_id)
    confirmation = client.post(f"/tasks/{task['task_id']}/confirmation", headers=actor).json()
    assert client.post("/reservations", headers=actor, json={"confirmation_id": confirmation["confirmation_id"],
        "task_id": task["task_id"], "version": task["version"], "reward_atomic": task["reward_atomic"],
        "confirmed": True, "idempotency_key": "second-image-reservation"}).status_code == 200
    post = next(p for p in client.get("/me/jobs", headers=buyer).json()["jobs"] if p["id"] == job_id)
    assert post["publication_status"] == "no_available_tasks" and post["open_slots"] == 0
    assert job_id not in [p["id"] for p in client.get("/me/jobs", headers=stranger).json()["jobs"]]


def test_non_towel_video_uses_its_own_post_criteria(pg, flow, video):
    client, buyer, actor, _, _, _ = flow
    plan = {**image_plan(), "media_type": "video", "max_seconds": 30}
    created = client.post("/jobs", headers=buyer, json=plan).json()
    assert client.post(f"/jobs/{created['id']}/fixture-publish", headers=buyer,
        json={"plan_hash": created["plan_hash"], "confirmed": True}).status_code == 200
    task = next(t for t in client.get("/tasks?equipment=phone", headers=actor).json()["tasks"] if t["job_id"] == created["id"])
    confirmation = client.post(f"/tasks/{task['task_id']}/confirmation", headers=actor).json()
    reservation = client.post("/reservations", headers=actor, json={"confirmation_id": confirmation["confirmation_id"],
        "task_id": task["task_id"], "version": task["version"], "reward_atomic": task["reward_atomic"],
        "confirmed": True, "idempotency_key": "general-video-reservation"}).json()
    uploaded = client.post(f"/reservations/{reservation['id']}/media?rights_ack=true", content=video,
        headers={**actor, "Content-Type": "video/mp4"})
    assert uploaded.status_code == 200
    assert run_once(pg)
    findings = client.get(f"/submissions/{uploaded.json()['id']}", headers=buyer).json()["findings"]
    assert findings["decoded"] and len(findings["frames"]) == 5
    assert "cat_climbing_tree" in findings["assessment"] and "large_towel" not in findings["assessment"]


def test_bounded_image_decoder_rejects_too_large_or_animated(tmp_path):
    storage = LocalStorage(tmp_path)
    path = storage.path("a" * 32 + ".image")
    path.write_bytes(image_bytes(size=(8193, 240)))
    with pytest.raises(InvalidMedia): inspect_image(path, storage)
    image = Image.new("RGB", (320, 240), "red")
    image.save(path, "PNG", save_all=True, append_images=[Image.new("RGB", (320, 240), "blue")])
    with pytest.raises(InvalidMedia): inspect_image(path, storage)


@pytest.mark.parametrize("bad", [False, True])
def test_generic_verification_uses_exact_post_criteria_and_cited_samples(bad):
    criterion = dict(result="uncertain", explanation="A still cannot prove a complete climbing action", timestamps_ms=[1 if bad else 0])
    payload = {"checks": {key: criterion for key in ["task_completion", "visibility", "cat_climbing_tree"]}}
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    adapter = GeminiFrames("test-only", "verified-test-model", httpx.MockTransport(respond))
    if bad:
        with pytest.raises(ProviderFailure): adapter.assess_post([(0, image_bytes("JPEG"))], image_plan(), 0)
    else:
        result = adapter.assess_post([(0, image_bytes("JPEG"))], image_plan(), 0)
        assert result.checks["cat_climbing_tree"].result == "uncertain"
    assert "Cat climbing a tree" in requests[0]["contents"][0]["parts"][0]["text"]
    assert "towel" not in requests[0]["systemInstruction"]["parts"][0]["text"]


@pytest.mark.parametrize("consent", [True, False])
def test_image_worker_calls_model_only_for_consented_media(tmp_path, monkeypatch, consent):
    import framebounty.worker as worker
    storage = LocalStorage(tmp_path)
    key = "b" * 32 + ".image"
    storage.path(key).write_bytes(image_bytes())
    calls = []
    criterion = dict(result="fail", explanation="Synthetic color card contains no cat or tree", timestamps_ms=[0])
    payload = {"checks": {key: criterion for key in ["task_completion", "visibility", "cat_climbing_tree"]}}
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(payload)}]}}]})
    monkeypatch.setenv("ALLOW_MODEL_MEDIA", "true")
    monkeypatch.setattr(worker, "GeminiFrames", lambda *args: GeminiFrames("test-only", "verified-test-model", httpx.MockTransport(respond)))
    findings = worker.analyze(storage, key, image_plan(), False, "image/png", consent)
    if consent:
        assert len(calls) == 1 and findings["assessment"]["task_completion"]["result"] == "fail"
    else:
        assert calls == [] and findings["assessment"] is None and "provider_error" in findings
