"""Bounded raw-body mobile upload and authorized media/review endpoints."""
import asyncio
import hashlib
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .auth import current_wallet
from .db import session
from .marketplace import new_id
from .media import MAX_UPLOAD, InvalidMedia, LocalStorage, validate_container_header, validate_image_header
from .models import Job, Submission
from .planning import next_collection_batch, next_fixture_batch, publish_fixture
from .submissions import coverage, finalize_upload, owned_reservation, private_submission, release_expired, review, submission_view

router = APIRouter()


@router.post("/reservations/{reservation_id}/media")
@router.post("/reservations/{reservation_id}/image")
@router.post("/reservations/{reservation_id}/video")
async def upload(reservation_id: str, request: Request, rights_ack: bool = False, model_ack: bool = False,
                 wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    reservation = owned_reservation(db, reservation_id, wallet)
    job = db.get(Job, reservation.job_id)
    kind = job.plan.get("media_type", "video")
    endpoint = request.url.path.rsplit("/", 1)[-1]
    if endpoint != "media" and endpoint != kind:
        raise HTTPException(415, "This post requires " + kind + " submissions")
    validate_header = validate_image_header if kind == "image" else validate_container_header
    allowed_mimes = {"image/jpeg", "image/png"} if kind == "image" else {"video/mp4", "video/quicktime"}
    limit = 20 * 1024 * 1024 if kind == "image" else MAX_UPLOAD
    if not rights_ack:
        raise HTTPException(422, "Explicit acknowledgment of this task's usage rights is required")
    # Existing uploads may be retried by content hash after the original deadline.
    previous = db.scalar(select(Submission.id).where(Submission.reservation_id == reservation_id))
    if not previous and (reservation.state not in {"fixture_reserved", "reserved"} or reservation.expires_at <= datetime.now(UTC)):
        raise HTTPException(409, "Reservation no longer accepts uploads")
    mime = request.headers.get("content-type", "").split(";")[0].lower()
    if mime not in allowed_mimes:
        raise HTTPException(415, "Use JPEG/PNG for image posts or MP4/MOV for video posts")
    try:
        declared = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise HTTPException(400, "Invalid upload size") from exc
    if declared < 0 or declared > limit:
        raise HTTPException(413, "Media exceeds this post type upload limit")
    db.rollback()  # No budget locks or database transaction during network streaming.
    storage = LocalStorage()
    name = new_id()
    temporary, final = storage.path(name + ".upload"), storage.path(name + "." + kind)
    digest, count, header, retained = hashlib.sha256(), 0, b"", False
    try:
        async with asyncio.timeout(120):
            with temporary.open("xb") as target:
                async for chunk in request.stream():
                    count += len(chunk)
                    if count > limit:
                        raise HTTPException(413, "Media exceeds this post type upload limit")
                    header = (header + chunk[:12])[:12]
                    if len(header) >= 12:
                        validate_header(header)
                    digest.update(chunk)
                    target.write(chunk)
        validate_header(header)
        if declared and declared != count:
            raise HTTPException(400, "Upload was truncated")
        temporary.replace(final)
        item = finalize_upload(db, wallet, reservation_id, name + "." + kind, digest.hexdigest(), count, mime, model_ack)
        retained = item.object_key == name + "." + kind
        return submission_view(item)
    except InvalidMedia as exc:
        raise HTTPException(422, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(408, "Upload timed out; retry the same video") from exc
    except SQLAlchemyError:
        # A disconnect during COMMIT has an uncertain outcome. Preserve the private
        # object for reconciliation instead of deleting media a committed row may own.
        retained = final.exists()
        raise
    finally:
        temporary.unlink(missing_ok=True)
        if not retained:
            final.unlink(missing_ok=True)


@router.get("/submissions/{submission_id}")
def get_submission(submission_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = private_submission(db, submission_id, wallet)
    job = db.get(Job, item.job_id)
    return submission_view(item, include_private_pairs=wallet in (job.buyer, job.reviewer))


@router.get("/submissions/{submission_id}/media")
@router.get("/submissions/{submission_id}/video")
def video(submission_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = private_submission(db, submission_id, wallet)
    from .previews import owns_original, preview_response
    if not owns_original(item, wallet):
        if item.content_type.startswith("image/"): return preview_response(item)
        raise HTTPException(403, "Original video unlocks after confirmed payment; use the watermarked preview")
    path = LocalStorage().path(item.object_key)
    if not path.is_file():
        raise HTTPException(404, "Video object is unavailable")
    return FileResponse(path, media_type=item.content_type, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/submissions/{submission_id}/frames/{index}")
def frame(submission_id: str, index: int, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = private_submission(db, submission_id, wallet)
    frames = item.findings.get("frames", [])
    if index < 0 or index >= len(frames):
        raise HTTPException(404, "Frame not found")
    from .previews import owns_original, preview_response
    if not owns_original(item, wallet): return preview_response(item, index)
    path = LocalStorage().path(frames[index]["key"])
    if not path.is_file():
        raise HTTPException(404, "Frame object is unavailable")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@router.get("/submissions/{submission_id}/preview")
def preview(submission_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    from .previews import preview_response
    return preview_response(private_submission(db, submission_id, wallet))


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern=r"^(accept|reject)$")
    task_completed: bool = Field(strict=True)
    watched_full_video: bool = Field(strict=True)
    tags: list[str] = Field(max_length=10)
    reason: str = Field(min_length=3, max_length=1000)


@router.post("/submissions/{submission_id}/review")
def decide(submission_id: str, body: ReviewRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    return submission_view(review(db, wallet, submission_id, **body.model_dump()), include_private_pairs=True)


def owned_job(db: Session, job_id: str, wallet: str) -> Job:
    job = db.get(Job, job_id)
    if job is None or wallet not in (job.buyer, job.reviewer):
        raise HTTPException(404, "Job not found")
    return job


@router.get("/jobs/{job_id}/reviews")
def queue(job_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    owned_job(db, job_id, wallet)
    items = db.scalars(select(Submission).where(Submission.job_id == job_id).order_by(Submission.created_at).limit(100)).all()
    return {"submissions": [submission_view(item, include_private_pairs=True) for item in items]}


@router.get("/jobs/{job_id}/coverage")
def get_coverage(job_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    return coverage(db, owned_job(db, job_id, wallet))


@router.get("/jobs/{job_id}/export")
def export(job_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    job = owned_job(db, job_id, wallet)
    items = db.scalars(select(Submission).where(Submission.job_id == job.id, Submission.state.in_(["fixture_accepted", "accepted"])).order_by(Submission.id)).all()
    return {"job_id": job.id, "fixture": job.fixture, "plan": job.plan, "items": [
        {"submission_id": item.id, "sha256": item.sha256, "reviewed_tags": item.reviewed_tags,
         "rubric_hash": item.rubric_hash, "rights_declaration": item.rights_declaration,
         "media_type": job.plan.get("media_type", "video"),
         "authenticated_media_path": f"/submissions/{item.id}/media",
         "authenticated_video_path": f"/submissions/{item.id}/video" if item.content_type.startswith("video/") else None} for item in items]}


@router.post("/reservations/{reservation_id}/release-expired")
def expire(reservation_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    item = release_expired(db, reservation_id, wallet)
    return {"id": item.id, "state": item.state}


@router.get("/jobs/{job_id}/dataset.zip")
def export_dataset(job_id: str, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    import zipstream
    job = owned_job(db, job_id, wallet)
    items = db.scalars(select(Submission).where(Submission.job_id == job.id, Submission.state.in_(["fixture_accepted", "accepted"])).order_by(Submission.id)).all()
    if len(items) > job.plan["total"]:
        raise HTTPException(409, "Accepted data exceeds the approved plan; export requires reconciliation")
    archive = zipstream.ZipStream(compress_type=zipstream.ZIP_STORED)
    storage = LocalStorage()
    records = []
    total_bytes = 0
    for item in items:
        source = storage.path(item.object_key)
        if not source.is_file():
            raise HTTPException(409, "An accepted media object is missing; export requires storage repair")
        # Archive paths contain only server-generated identifiers, never filenames
        # from contributors. Stored ZIP streams avoid compression CPU and temp copies.
        extension = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4", "video/quicktime": "mov"}[item.content_type]
        folder = "images" if item.content_type.startswith("image/") else "videos"
        name = f"{folder}/{item.id}.{extension}"
        archive.add_path(str(source), name)
        total_bytes += source.stat().st_size
        records.append({"submission_id": item.id, "path": name, "sha256": item.sha256,
            "reviewed_tags": item.reviewed_tags, "rubric_hash": item.rubric_hash,
            "rights_declaration": item.rights_declaration})
    archive.add(json.dumps({"job_id": job.id, "fixture": job.fixture, "plan": job.plan, "items": records}, indent=2).encode(), "manifest.json")
    return StreamingResponse(archive, media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="framebounty-{job.id}.zip"', "Cache-Control": "private, no-store", "X-Data-Bytes": str(total_bytes)})


class FixturePublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: bool = Field(strict=True)


@router.post("/jobs/{job_id}/fixture-publish")
def publish(job_id: str, body: FixturePublishRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    if not body.confirmed:
        raise HTTPException(422, "Explicit confirmation of simulated funding is required")
    ids = publish_fixture(db, wallet, job_id, body.plan_hash)
    return {"task_ids": ids, "fixture": True, "message": "Simulated funds only; no blockchain transaction occurred"}


class BatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{8,64}$")


@router.post("/jobs/{job_id}/next-fixture-batch")
def next_batch(job_id: str, body: BatchRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    return next_fixture_batch(db, wallet, job_id, body.request_id)


@router.post("/jobs/{job_id}/next-batch")
def next_live_batch(job_id: str, body: BatchRequest, wallet: str = Depends(current_wallet), db: Session = Depends(session)):
    return next_collection_batch(db, wallet, job_id, body.request_id)
