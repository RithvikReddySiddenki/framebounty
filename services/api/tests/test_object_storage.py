"""Real private files/PostgreSQL/Pillow; only Supabase HTTP is simulated."""
import httpx
import pytest
from sqlalchemy.orm import Session

from framebounty import object_storage as objects
from framebounty.media import InvalidMedia, MediaUnavailable
from framebounty.models import Submission, Job
from framebounty.worker import run_once
from test_postgres import pg
from test_submission_flow import flow
from test_automatic_verification import uploaded_ai
from test_image_posts import image_bytes


@pytest.fixture(params=["legacy", "secret"])
def remote(monkeypatch, request):
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "synthetic-server-only-secret")
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    modern = request.param == "secret"
    if modern: monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_synthetic-test-only")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "framebounty-media")
    state = {"objects": {}, "public": False, "fail_write": False, "calls": []}
    def respond(request):
        if modern:
            assert request.headers["apikey"] == "sb_secret_synthetic-test-only"
            assert "authorization" not in request.headers
        else:
            assert request.headers["Authorization"] == "Bearer synthetic-server-only-secret"
        assert request.url.host == "example.supabase.co"
        state["calls"].append((request.method, request.url.path))
        if "/bucket/" in request.url.path:
            return httpx.Response(200, json={"public": state["public"]})
        key = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            if state["fail_write"]: return httpx.Response(503, text="private upstream details")
            assert request.headers["x-upsert"] == "false"
            if key in state["objects"]: return httpx.Response(409)
            state["objects"][key] = request.read()
            return httpx.Response(200, json={"Key": key})
        if key not in state["objects"]: return httpx.Response(404)
        return httpx.Response(200, content=state["objects"][key])
    implementation = objects.SupabaseStorage
    monkeypatch.setattr(objects, "SupabaseStorage", lambda root=None: implementation(root, httpx.MockTransport(respond)))
    return state


def test_private_object_roundtrip_survives_a_different_worker_cache(remote, tmp_path):
    writer = objects.SupabaseStorage(tmp_path / "writer")
    reader = objects.SupabaseStorage(tmp_path / "reader")
    key = "a" * 32 + ".image"
    writer.path(key).write_bytes(b"private image")
    writer.persist(key, "image/png")
    assert not reader.path(key).exists()
    assert reader.materialize(key).read_bytes() == b"private image"
    with pytest.raises(InvalidMedia): reader.materialize("../private")
    assert not reader.materialize("b" * 32 + ".image").exists()


def test_public_bucket_and_provider_outage_fail_closed(remote, tmp_path):
    storage = objects.SupabaseStorage(tmp_path)
    key = "a" * 32 + ".jpg"
    storage.path(key).write_bytes(b"frame")
    remote["public"] = True
    with pytest.raises(MediaUnavailable): storage.persist(key, "image/jpeg")
    with pytest.raises(MediaUnavailable): storage.materialize(key)  # Cached bytes also require private bucket configuration.
    assert remote["objects"] == {}
    remote["public"], remote["fail_write"] = False, True
    with pytest.raises(MediaUnavailable) as error: storage.persist(key, "image/jpeg")
    assert "private upstream" not in str(error.value)


def test_oversized_download_never_publishes_partial_cache(remote, tmp_path, monkeypatch):
    key = "a" * 32 + ".video"
    remote["objects"][key] = b"123456789"
    monkeypatch.setattr(objects, "MAX_UPLOAD", 8)
    storage = objects.SupabaseStorage(tmp_path)
    with pytest.raises(MediaUnavailable): storage.materialize(key)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("url", ["http://example.supabase.co", "https://attacker.invalid", "https://example.supabase.co/path"])
def test_untrusted_storage_endpoint_is_rejected(remote, tmp_path, monkeypatch, url):
    monkeypatch.setenv("SUPABASE_URL", url)
    with pytest.raises(MediaUnavailable): objects.SupabaseStorage(tmp_path)
    assert remote["calls"] == []


def test_originals_and_watermarks_remain_gated_after_remote_restore(pg, flow, remote, monkeypatch, tmp_path):
    client, buyer, actor, stranger, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "pass")
    jid, sid = uploaded_ai(client, buyer, actor)
    assert len(remote["objects"]) == 1
    # A separate worker has no copy of the API's original upload.
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "worker-cache"))
    assert run_once(pg)
    assert len(remote["objects"]) == 2  # Original and durable metadata-free sample.
    assert client.get(f"/submissions/{sid}", headers=actor).json()["state"] == "verified"
    # A third API instance restores frames and original from object storage.
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path / "reader-cache"))
    assert client.get(f"/submissions/{sid}/media", headers=stranger).status_code == 404
    before = client.get(f"/submissions/{sid}/media", headers=buyer)
    assert before.status_code == 200 and before.content != image_bytes()
    assert client.get(f"/jobs/{jid}/export", headers=buyer).json()["items"] == []
    assert client.get(f"/submissions/{sid}/media", headers=actor).content == image_bytes()
    assert client.post(f"/jobs/{jid}/release-funds", headers=buyer,
        json={"confirmed": True, "request_id": "remote-release-request"}).json()["confirmed"]
    assert client.get(f"/submissions/{sid}/media", headers=buyer).content == image_bytes()
    assert client.get(f"/jobs/{jid}/dataset.zip", headers=buyer).status_code == 200


def test_frame_storage_failure_cannot_become_quality_approval(pg, flow, remote, monkeypatch):
    client, buyer, actor, _, _, _ = flow
    monkeypatch.setenv("FIXTURE_VERIFICATION_RESULT", "pass")
    jid, sid = uploaded_ai(client, buyer, actor)
    remote["fail_write"] = True
    assert run_once(pg)
    with Session(pg) as db:
        item = db.get(Submission, sid)
        assert item.state == "queued" and not item.findings.get("decoded")
        assert db.get(Job, jid).paid_atomic == 0


def test_upload_storage_outage_never_creates_a_successful_submission(pg, flow, remote):
    from test_image_posts import reserve_image
    from sqlalchemy import select
    client, buyer, actor, _, _, _ = flow
    _, reservation = reserve_image(client, buyer, actor)
    remote["fail_write"] = True
    response = client.post(f"/reservations/{reservation}/image?rights_ack=true&model_ack=true",
        headers={**actor, "Content-Type": "image/png"}, content=image_bytes())
    assert response.status_code == 503 and "private upstream" not in response.text
    with Session(pg) as db:
        assert db.scalar(select(Submission).where(Submission.reservation_id == reservation)) is None
