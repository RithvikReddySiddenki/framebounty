"""PostgreSQL leased verification jobs with fenced completion and bounded retries.

Slow media/model processing runs outside database transactions. A worker that loses
its lease cannot overwrite a new owner's result. Workers can reject qualifying failures; they cannot pay.
"""
import argparse
import os
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .db import engine
from .marketplace import new_id
from .media import InvalidMedia, LocalStorage, MediaUnavailable, decode_video, inspect_video, inspect_image, sample_frames
from .models import Job, Submission, VerificationJob
from .verification import GeminiFrames, ProviderFailure, fixture_assessment, generic_fixture_assessment
from .automatic_verification import automatic, evaluate


def claim(db: Session) -> tuple[str, str] | None:
    now = datetime.now(UTC)
    exhausted = db.scalars(select(VerificationJob).where(VerificationJob.state == "leased",
        VerificationJob.attempts >= 3, VerificationJob.lease_until <= now).with_for_update(skip_locked=True).limit(50)).all()
    for old in exhausted:
        old.state, old.lease_token, old.lease_until = "failed", None, None
        submission = db.get(Submission, old.submission_id)
        if submission.state in ("queued", "verifying"):
            submission.state, submission.findings = "needs_review", {"decoded": False, "processing_error": "Worker lease exhausted after restart; manual infrastructure repair required"}
    item = db.scalar(select(VerificationJob).where(
        VerificationJob.attempts < 3,
        or_((VerificationJob.state == "queued") & or_(VerificationJob.lease_until.is_(None), VerificationJob.lease_until <= now),
            (VerificationJob.state == "leased") & (VerificationJob.lease_until <= now)),
    ).order_by(VerificationJob.id).with_for_update(skip_locked=True).limit(1))
    if item is None:
        db.commit()
        return None
    item.state, item.lease_token, item.lease_until = "leased", new_id(), now + timedelta(minutes=5)
    item.attempts += 1
    submission = db.get(Submission, item.submission_id)
    if submission.state not in ("queued", "verifying"):
        item.state, item.lease_token, item.lease_until = "cancelled", None, None
        db.commit()
        return None
    submission.state = "verifying"
    db.commit()
    return item.id, item.lease_token


def analyze(storage: LocalStorage, key: str, rubric: dict, fixture: bool, content_type: str | None = None, model_consent: bool = False) -> dict:
    path = storage.path(key)
    kind = rubric.get("media_type", "video")
    if kind == "image":
        metadata_dict, frames = inspect_image(path, storage, content_type)
        duration_ms = 0
    else:
        metadata = inspect_video(path)
        if not rubric["min_seconds"] * 1000 <= metadata.duration_ms <= rubric["max_seconds"] * 1000:
            raise InvalidMedia("Video duration does not match this post's requirements")
        decode_video(path)
        frames = sample_frames(path, storage, metadata.duration_ms)
        metadata_dict, duration_ms = asdict(metadata), metadata.duration_ms
    findings = {"decoded": True, "media_type": kind, "metadata": metadata_dict, "frames": frames,
                "limitations": "AI checks can be uncertain and do not prove consent or authenticity. Samples cannot establish every action. Human review authorizes payment."}
    try:
        if fixture:
            assessment = fixture_assessment() if "media_type" not in rubric else generic_fixture_assessment(rubric)
            if rubric.get("verification_policy", "ai") == "ai":
                result = os.getenv("FIXTURE_VERIFICATION_RESULT", "uncertain")
                if result not in {"pass", "fail", "uncertain"}: result = "uncertain"
                assessment = generic_fixture_assessment(rubric)
                assessment = assessment.model_copy(update={"checks": {key: value.model_copy(update={
                    "result": result, "confidence": 100 if result != "uncertain" else 0,
                    "explanation": "Simulated verification only; no AI inspected this media."}) for key, value in assessment.checks.items()}})
        else:
            if os.getenv("ALLOW_MODEL_MEDIA") != "true" or not model_consent:
                raise ProviderFailure("Sending private media to Gemini requires explicit ALLOW_MODEL_MEDIA=true consent")
            adapter = GeminiFrames(os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_MODEL", ""))
            samples = [(frame["timestamp_ms"], storage.path(frame["key"]).read_bytes()) for frame in frames]
            assessment = adapter.assess(samples, str(rubric), duration_ms) if "media_type" not in rubric else adapter.assess_post(samples, rubric, duration_ms)
        findings["assessment"] = assessment.model_dump().get("checks", assessment.model_dump())
    except ProviderFailure as exc:
        findings["provider_error"] = str(exc)
        findings["assessment"] = None
    return findings


def finish(db: Session, job_id: str, lease_token: str, findings: dict | None, error: str | None = None, invalid: bool = False) -> bool:
    item = db.scalar(select(VerificationJob).where(VerificationJob.id == job_id).with_for_update().execution_options(populate_existing=True))
    if item is None or item.state != "leased" or item.lease_token != lease_token or item.lease_until <= datetime.now(UTC):
        return False
    submission = db.scalar(select(Submission).where(Submission.id == item.submission_id).with_for_update())
    if submission.state not in ("queued", "verifying"):
        item.state, item.lease_token, item.lease_until = "cancelled", None, None
        db.commit()
        return False
    consent = submission.findings.get("model_consent", False)
    if error and not invalid and item.attempts < 3:
        item.state = "queued"
        submission.state = "queued"
        submission.findings = {"processing_error": error, "retry_attempt": item.attempts, "model_consent": consent}
    else:
        item.state = "failed" if error else "done"
        submission.state = "invalid" if invalid else "needs_review"
        submission.findings = {**(findings or {"processing_error": error, "decoded": False}), "model_consent": consent}
    item.lease_until = datetime.now(UTC) + timedelta(seconds=2 ** item.attempts) if item.state == "queued" else None
    item.lease_token = None
    db.commit()
    return True


def run_once(db_engine=None, storage: LocalStorage | None = None) -> bool:
    db_engine, storage = db_engine or engine(), storage or LocalStorage()
    # Recover a crash between durable decoding and policy evaluation. This path
    # cannot pay and rechecks reservation state under financial row locks.
    with Session(db_engine) as db:
        candidates = db.scalars(select(Submission.id).join(Job, Submission.job_id == Job.id).where(
            Submission.state.in_(["needs_review", "invalid"]),
            or_(Job.plan["verification_policy"].as_string().is_(None), Job.plan["verification_policy"].as_string() == "ai")).limit(20)).all()
    for candidate in candidates:
        with Session(db_engine) as db: evaluate(db, candidate)
    with Session(db_engine) as db:
        claimed = claim(db)
        if claimed is None:
            return False
        job_id, token = claimed
        work = db.get(VerificationJob, job_id)
        submission = db.get(Submission, work.submission_id)
        job = db.get(Job, submission.job_id)
        key, rubric, fixture, digest = submission.object_key, job.plan, job.fixture, submission.sha256
        submission_id, content_type = submission.id, submission.content_type
        model_consent = submission.findings.get("model_consent", False)
    findings, error, invalid = None, None, False
    try:
        findings = analyze(storage, key, rubric, fixture, content_type, model_consent)
        with Session(db_engine) as db:
            # Only disclose duplicate candidates within the same private job.
            exact = db.scalars(select(Submission.id).where(Submission.job_id == job.id,
                Submission.id != submission_id, Submission.sha256 == digest)).all()
            findings["exact_duplicate_candidates"] = list(exact)
            others = db.scalars(select(Submission).where(Submission.job_id == job.id,
                Submission.id != submission_id, Submission.state.in_(["needs_review", "fixture_accepted", "accepted"])).limit(100)).all()
            import imagehash
            hashes = [imagehash.hex_to_hash(frame["dhash"]) for frame in findings["frames"]]
            findings["perceptual_duplicate_candidates"] = [other.id for other in others
                if sum(any(imagehash.hex_to_hash(frame["dhash"]) - current <= 4
                           for frame in other.findings.get("frames", [])) for current in hashes) >= min(3, len(hashes))]
            findings["duplicate_notice"] = "Similarity is a review flag; separate recordings of repeated tasks may look alike. It never rejects work automatically."
    except InvalidMedia as exc:
        error, invalid = str(exc), True
    except (MediaUnavailable, OSError) as exc:
        error = type(exc).__name__ + ": verification infrastructure unavailable"
    with Session(db_engine) as db:
        committed = finish(db, job_id, token, findings, error, invalid)
    if committed:
        with Session(db_engine) as db: evaluate(db, submission_id)
    if not committed and findings:
        for frame in findings.get("frames", []):
            storage.path(frame["key"]).unlink(missing_ok=True)
    return True


def main():
    parser = argparse.ArgumentParser(description="Run durable verification; never approves quality or sends payments")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    while True:
        worked = run_once()
        if args.once:
            import json
            print(json.dumps({"processed": worked}))
            return
        if not worked:
            time.sleep(2)


if __name__ == "__main__":
    main()
