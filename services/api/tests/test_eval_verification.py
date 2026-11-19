"""Offline check of scripts/eval_verification.py with a fake Gemini (no network)."""
import importlib.util
import json
import subprocess
from pathlib import Path

import httpx
import pytest

from framebounty.media import media_executable
from framebounty.verification import GeminiFrames

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("eval_verification", ROOT / "scripts/eval_verification.py")
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def check(result, confidence=90):
    return {"result": result, "confidence": confidence, "explanation": "synthetic", "timestamps_ms": []}


def fake_gemini(overrides_per_call, calls):
    """Answers 'pass' for every check the request's schema asks for, with per-call overrides."""
    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        keys = body["generationConfig"]["responseJsonSchema"]["properties"]["checks"]["required"]
        checks = {k: check("pass") for k in keys} | overrides_per_call[len(calls) - 1]
        text = json.dumps({"checks": checks})
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]})
    return GeminiFrames("test-key", "fake-model", transport=httpx.MockTransport(handler))


def make_clips(folder, names):
    folder.mkdir()
    for name in names:
        subprocess.run([media_executable("ffmpeg"), "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15",
                        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(folder / name)], check=True, timeout=60)


def test_decide_mirrors_the_app_policy():
    mandatory = {"task_completion", "visibility", "large_towel"}
    passing = {k: check("pass") for k in mandatory}
    assert evaluation.decide(passing, mandatory) == "pay"
    assert evaluation.decide({**passing, "large_towel": check("fail", 95)}, mandatory) == "reject"
    assert evaluation.decide({**passing, "large_towel": check("pass", 79)}, mandatory) == "uncertain"
    assert evaluation.decide({**passing, "large_towel": check("fail", 50)}, mandatory) == "uncertain"


def test_generic_rows_build_a_post_for_any_task():
    base = evaluation_base_plan()
    row = {"file": "pour.mp4", "task": "Pour water from a bottle into a glass",
           "requirements": "clear_glass: The glass is transparent | full_glass: The glass ends at least half full",
           "task_completion": "pass", "visibility": "pass", "expected": "clear_glass=pass; full_glass=fail"}
    rubric, labels, mandatory = evaluation.clip_case(row, base)
    assert rubric["title"] == "Pour water from a bottle into a glass"
    assert [r["key"] for r in rubric["requirements"]] == ["clear_glass", "full_glass"]
    assert mandatory == {"task_completion", "visibility", "clear_glass", "full_glass"}
    assert evaluation.expected_decision(labels, mandatory) == "reject"
    with pytest.raises(SystemExit, match="invalid task/requirements"):
        evaluation.clip_case({**row, "requirements": "Bad Key: description here"}, base)


def evaluation_base_plan():
    from framebounty.demo import example_plan
    return example_plan().model_dump(mode="json")


@pytest.mark.skipif(not media_executable("ffmpeg"), reason="FFmpeg required")
def test_eval_scores_generic_and_towel_clips(tmp_path):
    clips = tmp_path / "clips"
    make_clips(clips, ["pour.mp4", "stack.mp4", "towel.mp4"])
    (clips / "labels.csv").write_text(
        "file,task,requirements,task_completion,visibility,expected,task_tags,large_towel,dark_surface\n"
        'pour.mp4,Pour water from a bottle into a glass,clear_glass: The glass is transparent,pass,pass,clear_glass=pass,,,\n'
        "stack.mp4,Stack three cups into a tower,,fail,pass,,,,\n"
        "towel.mp4,,,pass,pass,,large_towel,pass,fail\n"
        "missing.mp4,Open a drawer,,pass,pass,,,,\n")
    calls = []
    adapter = fake_gemini([{}, {"task_completion": check("fail", 95)}, {"dark_surface": check("fail", 85)}], calls)
    out = tmp_path / "out"
    assert evaluation.main(["--clips", str(clips), "--labels", str(clips / "labels.csv"),
                            "--sleep", "0", "--out", str(out)], adapter=adapter) == 0
    data = json.loads((out / "results.json").read_text())
    summary = data["summary"]
    assert summary["scored"] == 3 and summary["errors"] == 1
    assert summary["correct"] == 3 and summary["false_pay"] == 0
    by_file = {r["file"]: r for r in data["results"]}
    assert by_file["pour.mp4"]["decision"] == "pay"
    assert by_file["stack.mp4"]["decision"] == "reject"
    assert by_file["towel.mp4"]["decision"] == "pay"  # dark_surface not required for a large_towel task
    # Each request carries the clip's own task, and 5 frames.
    assert "Pour water from a bottle into a glass" in json.dumps(calls[0]["contents"])
    assert len([p for p in calls[0]["contents"][0]["parts"] if "inlineData" in p]) == 5
    assert "False pay" in (out / "report.md").read_text(encoding="utf-8")
