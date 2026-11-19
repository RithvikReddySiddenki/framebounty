"""Measure real AI verification accuracy on labeled clips of any simple task, offline.

Uses the app's own pipeline (ffprobe/ffmpeg decode, the same 5 sampled frames,
GeminiFrames.assess_post and the same >=80 confidence policy) without a
database, wallet or chain. Each clip can describe its own task, so the test
covers general movements (pouring, stacking, opening a drawer, ...), not just
the towel demo. Sends frames to Gemini: only use clips you recorded yourself.

Labels CSV (header required). Generic format, one task per row:
  file             clip file name inside --clips (MP4/MOV 10-30 s, or JPG/PNG)
  task             what the buyer asked for, e.g. "Pour water from a bottle into a glass"
  requirements     optional extra checks: "key: description | key2: description"
                   keys are lowercase_with_underscores, e.g. "clear_glass: The glass is transparent"
  task_completion  pass | fail   was the task actually completed?
  visibility       pass | fail   were the hands and objects clearly visible?
  expected         labels for the extra checks: "clear_glass=pass; full_glass=fail"
  task_tags        optional; requirement keys the reserved task demands
                   (default: all listed requirements are mandatory)

Legacy towel format (no 'task' column): file, task_completion, visibility,
large_towel, dark_surface, task_tags, evaluated against the demo towel plan.

Example:
  python scripts/eval_verification.py --clips clips --labels clips/labels.csv --model gemini-3.5-flash-lite
"""
import argparse
import csv
import json
import os
import secrets
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

THRESHOLD = 80  # mirrors automatic_verification.THRESHOLD
BASE_CHECKS = ["task_completion", "visibility"]


def decide(checks: dict, mandatory: set[str]) -> str:
    """Same rule as automatic_verification.evaluate (pure, no database)."""
    def confident(key, result):
        check = checks.get(key) or {}
        return check.get("result") == result and type(check.get("confidence")) is int and check["confidence"] >= THRESHOLD
    if any(confident(key, "fail") for key in mandatory):
        return "reject"
    if all(confident(key, "pass") for key in mandatory):
        return "pay"
    return "uncertain"


def parse_requirements(text: str) -> list[dict]:
    requirements = []
    for part in (text or "").split("|"):
        if not part.strip():
            continue
        key, _, description = part.partition(":")
        requirements.append({"key": key.strip(), "description": description.strip(), "minimum": 1})
    return requirements


def parse_expected(text: str) -> dict[str, str]:
    labels = {}
    for part in (text or "").split(";"):
        if "=" in part:
            key, _, value = part.partition("=")
            labels[key.strip()] = value.strip().lower()
    return labels


def clip_case(row: dict, base_plan: dict) -> tuple[dict, dict[str, str], set[str]]:
    """Returns (rubric, labels per check, mandatory checks) for one CSV row."""
    from framebounty.domain import Plan
    labels = {key: row.get(key, "").strip().lower() for key in BASE_CHECKS}
    if (row.get("task") or "").strip():
        requirements = parse_requirements(row.get("requirements", ""))
        plan = {**base_plan, "title": row["task"].strip(), "requirements": requirements,
                "total": max(1, min(20, len(requirements) or 1))}
        try:
            rubric = Plan.model_validate({**plan, "requirements": tuple(requirements)}).model_dump(mode="json")
        except Exception as exc:  # show the CSV author what to fix
            raise SystemExit(f"Row {row.get('file')}: invalid task/requirements ({exc})") from exc
        labels.update(parse_expected(row.get("expected", "")))
        keys = [r["key"] for r in requirements]
    else:
        rubric = base_plan
        keys = [r["key"] for r in base_plan["requirements"]]
        labels.update({key: row.get(key, "").strip().lower() for key in keys})
    tags_text = (row.get("task_tags") or "").strip()
    tags = {t.strip() for t in tags_text.split(";") if t.strip()} if tags_text or not row.get("task") else set(keys)
    unknown = tags - set(keys)
    if unknown:
        raise SystemExit(f"Row {row.get('file')}: task_tags {sorted(unknown)} are not listed requirements")
    return rubric, labels, {*BASE_CHECKS, *tags}


def expected_decision(labels: dict[str, str], mandatory: set[str]) -> str:
    return "pay" if all(labels.get(key) == "pass" for key in mandatory) else "reject"


def load_rows(labels: Path) -> list[dict]:
    with labels.open(newline="", encoding="utf-8-sig") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise SystemExit("Labels file has no rows")
    for row in rows:
        if not row.get("file"):
            raise SystemExit("Every label row needs a 'file' value")
    return rows


def assess_clip(path: Path, rubric: dict, adapter, storage) -> tuple[dict | None, str | None, int]:
    """Returns (checks, error, duration_ms) using the app's media helpers."""
    from framebounty.media import InvalidMedia, decode_video, inspect_image, inspect_video, sample_frames
    from framebounty.verification import ProviderFailure
    is_image = path.suffix.lower() in {".jpg", ".jpeg", ".png"}
    key = secrets.token_hex(16) + (".image" if is_image else ".video")  # the app's storage key format
    try:
        shutil.copyfile(path, storage.path(key))
        if is_image:
            _, frames = inspect_image(storage.path(key), storage, None)
            duration_ms, use_rubric = 0, {**rubric, "media_type": "image"}
        else:
            metadata = inspect_video(storage.path(key))
            if not rubric["min_seconds"] * 1000 <= metadata.duration_ms <= rubric["max_seconds"] * 1000:
                return None, f"duration {metadata.duration_ms} ms outside {rubric['min_seconds']}-{rubric['max_seconds']} s", metadata.duration_ms
            decode_video(storage.path(key))
            frames = sample_frames(storage.path(key), storage, metadata.duration_ms)
            duration_ms, use_rubric = metadata.duration_ms, rubric
        samples = [(f["timestamp_ms"], storage.path(f["key"]).read_bytes()) for f in frames]
        result = adapter.assess_post(samples, use_rubric, duration_ms)
        return result.model_dump()["checks"], None, duration_ms
    except (InvalidMedia, ProviderFailure, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}", 0


def main(argv=None, adapter=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--clips", required=True, type=Path)
    parser.add_argument("--labels", required=True, type=Path)
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", ""))
    parser.add_argument("--rubric", type=Path, help="Base plan JSON; defaults to the demo towel plan")
    parser.add_argument("--sleep", type=float, default=7.0, help="Seconds between model calls (free-tier rate limits)")
    parser.add_argument("--out", type=Path, default=Path(".local/eval"))
    args = parser.parse_args(argv)

    from framebounty.demo import example_plan
    from framebounty.media import LocalStorage
    from framebounty.verification import GeminiFrames
    base_plan = json.loads(args.rubric.read_text()) if args.rubric else example_plan().model_dump(mode="json")
    if adapter is None:
        adapter = GeminiFrames(os.getenv("GEMINI_API_KEY", ""), args.model)
    rows = load_rows(args.labels)
    cases = [clip_case(row, base_plan) for row in rows]  # validate every row before spending model calls
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    with tempfile.TemporaryDirectory() as scratch:
        storage = LocalStorage(scratch)
        for index, (row, (rubric, labels, mandatory)) in enumerate(zip(rows, cases)):
            path = args.clips / row["file"]
            base = {"file": row["file"], "task": rubric["title"], "mandatory": sorted(mandatory),
                    "expected": expected_decision(labels, mandatory)}
            if not path.is_file():
                results.append({**base, "decision": "error", "error": "missing file"})
                continue
            if index:
                time.sleep(args.sleep)
            started = time.monotonic()
            checks, error, duration = assess_clip(path, rubric, adapter, storage)
            seconds = round(time.monotonic() - started, 2)
            entry = {**base, "seconds": seconds, "duration_ms": duration, "error": error, "checks": checks,
                     "decision": decide(checks, mandatory) if checks else "error",
                     "criteria": {key: {"label": label, "model": (checks or {}).get(key, {}).get("result"),
                                        "confidence": (checks or {}).get(key, {}).get("confidence")}
                                  for key, label in labels.items() if label}}
            results.append(entry)
            print(f"[{index + 1}/{len(rows)}] {row['file']} ({rubric['title']}): expected {entry['expected']}, "
                  f"got {entry['decision']} ({seconds}s)" + (f" — {error}" if error else ""), flush=True)

    scored = [r for r in results if r["decision"] in {"pay", "reject", "uncertain"}]
    summary = {
        "model": args.model or "(injected)", "clips": len(results), "scored": len(scored),
        "errors": sum(1 for r in results if r["decision"] == "error"),
        "correct": sum(1 for r in scored if r["decision"] == r["expected"]),
        "false_pay": sum(1 for r in scored if r["decision"] == "pay" and r["expected"] == "reject"),
        "false_reject": sum(1 for r in scored if r["decision"] == "reject" and r["expected"] == "pay"),
        "uncertain": sum(1 for r in scored if r["decision"] == "uncertain"),
        "median_seconds": statistics.median([r["seconds"] for r in scored]) if scored else None,
    }
    per_criterion = {}
    for r in scored:
        for key, c in r["criteria"].items():
            stats = per_criterion.setdefault(key, {"agree": 0, "disagree": 0, "uncertain": 0})
            if c["model"] == "uncertain" or c["confidence"] is None or c["confidence"] < THRESHOLD:
                stats["uncertain"] += 1
            elif c["model"] == c["label"]:
                stats["agree"] += 1
            else:
                stats["disagree"] += 1
    summary["per_criterion"] = per_criterion

    (args.out / "results.json").write_text(json.dumps({"summary": summary, "results": results}, indent=2))
    lines = ["| Clip | Task | Expected | Model decision | Time (s) | Checks (model result, confidence vs label) |",
             "|---|---|---|---|---|---|"]
    for r in results:
        note = r.get("error") or "; ".join(f"{k}: {v['model']} {v['confidence']} (label {v['label']})"
                                           for k, v in r.get("criteria", {}).items())
        lines.append(f"| {r['file']} | {r['task']} | {r['expected']} | {r['decision']} | {r.get('seconds', '')} | {note} |")
    report = (f"# Verification accuracy ({summary['model']})\n\n"
              f"- Clips: {summary['clips']} · scored: {summary['scored']} · errors: {summary['errors']}\n"
              f"- **Correct decisions: {summary['correct']}/{summary['scored']}**\n"
              f"- **False pay (would pay bad work): {summary['false_pay']}** · false reject: {summary['false_reject']} · held as uncertain: {summary['uncertain']}\n"
              f"- Median time per clip: {summary['median_seconds']} s\n"
              f"- Per check (agree / disagree / uncertain): "
              + ", ".join(f"{k} {v['agree']}/{v['disagree']}/{v['uncertain']}" for k, v in per_criterion.items()) + "\n\n"
              + "\n".join(lines) + "\n")
    (args.out / "report.md").write_text(report, encoding="utf-8")
    print(f"\nWrote {args.out / 'report.md'} and results.json")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_criterion"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
