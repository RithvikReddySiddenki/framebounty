"""Measure real AI verification accuracy on labeled clips, offline.

Uses the app's own pipeline (ffprobe/ffmpeg decode, the same 5 sampled frames,
GeminiFrames.assess_post and the same >=80 confidence policy) without a
database, wallet or chain. Sends frames of the clips you list to Gemini, so
only use clips you recorded yourself or have permission to share.

Labels CSV columns (header required):
  file            clip file name inside --clips
  task_completion pass | fail   (did the person actually complete the fold?)
  visibility      pass | fail   (hands/towel clearly visible?)
  large_towel     pass | fail
  dark_surface    pass | fail
  task_tags       optional, ';'-separated tags the reserved task requires,
                  e.g. "large_towel;dark_surface" (empty = general task)

Example:
  $env:GEMINI_API_KEY="..."   # never commit it
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


def expected_decision(row: dict, mandatory: set[str]) -> str:
    return "pay" if all(row.get(key, "").strip().lower() == "pass" for key in mandatory) else "reject"


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
            image_rubric = {**rubric, "media_type": "image"}
            _, frames = inspect_image(storage.path(key), storage, None)
            duration_ms, use_rubric = 0, image_rubric
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
    parser.add_argument("--rubric", type=Path, help="Plan JSON; defaults to the demo towel plan")
    parser.add_argument("--sleep", type=float, default=7.0, help="Seconds between model calls (free-tier rate limits)")
    parser.add_argument("--out", type=Path, default=Path(".local/eval"))
    args = parser.parse_args(argv)

    from framebounty.demo import example_plan
    from framebounty.media import LocalStorage
    from framebounty.verification import GeminiFrames
    rubric = json.loads(args.rubric.read_text()) if args.rubric else example_plan().model_dump(mode="json")
    if adapter is None:
        adapter = GeminiFrames(os.getenv("GEMINI_API_KEY", ""), args.model)
    rows = load_rows(args.labels)
    args.out.mkdir(parents=True, exist_ok=True)

    results = []
    with tempfile.TemporaryDirectory() as scratch:
        storage = LocalStorage(scratch)
        for index, row in enumerate(rows):
            path = args.clips / row["file"]
            tags = {t.strip() for t in (row.get("task_tags") or "").split(";") if t.strip()}
            mandatory = {"task_completion", "visibility", *tags}
            if not path.is_file():
                results.append({"file": row["file"], "error": "missing file", "expected": expected_decision(row, mandatory)})
                continue
            if index:
                time.sleep(args.sleep)
            started = time.monotonic()
            checks, error, duration = assess_clip(path, rubric, adapter, storage)
            seconds = round(time.monotonic() - started, 2)
            entry = {"file": row["file"], "tags": sorted(tags), "seconds": seconds, "duration_ms": duration,
                     "expected": expected_decision(row, mandatory), "error": error, "checks": checks}
            entry["decision"] = decide(checks, mandatory) if checks else "error"
            entry["criteria"] = {key: {"label": row.get(key, "").strip().lower(),
                                       "model": (checks or {}).get(key, {}).get("result"),
                                       "confidence": (checks or {}).get(key, {}).get("confidence")}
                                 for key in ["task_completion", "visibility", "large_towel", "dark_surface"] if row.get(key)}
            results.append(entry)
            print(f"[{index + 1}/{len(rows)}] {row['file']}: expected {entry['expected']}, got {entry['decision']} ({seconds}s)"
                  + (f" — {error}" if error else ""), flush=True)

    scored = [r for r in results if r.get("decision") in {"pay", "reject", "uncertain"}]
    summary = {
        "model": args.model or "(injected)", "clips": len(results), "scored": len(scored),
        "errors": sum(1 for r in results if r.get("decision", "error") == "error" or r.get("error") == "missing file"),
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
    lines = ["| Clip | Tags | Expected | Model decision | Time (s) | Note |", "|---|---|---|---|---|---|"]
    for r in results:
        note = r.get("error") or "; ".join(f"{k}: {v['model']} {v['confidence']}" for k, v in r.get("criteria", {}).items())
        lines.append(f"| {r['file']} | {', '.join(r.get('tags', [])) or 'general'} | {r['expected']} | {r.get('decision', 'error')} | {r.get('seconds', '')} | {note} |")
    report = (f"# Verification accuracy ({summary['model']})\n\n"
              f"- Clips: {summary['clips']} · scored: {summary['scored']} · errors: {summary['errors']}\n"
              f"- **Correct decisions: {summary['correct']}/{summary['scored']}**\n"
              f"- **False pay (would pay bad work): {summary['false_pay']}** · false reject: {summary['false_reject']} · held as uncertain: {summary['uncertain']}\n"
              f"- Median time per clip: {summary['median_seconds']} s\n"
              f"- Per criterion (agree / disagree / uncertain): "
              + ", ".join(f"{k} {v['agree']}/{v['disagree']}/{v['uncertain']}" for k, v in per_criterion.items()) + "\n\n"
              + "\n".join(lines) + "\n")
    (args.out / "report.md").write_text(report, encoding="utf-8")
    print(f"\nWrote {args.out / 'report.md'} and results.json")
    print(json.dumps({k: v for k, v in summary.items() if k != "per_criterion"}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
