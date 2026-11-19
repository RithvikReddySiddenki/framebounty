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


def gemini_reply(checks):
    text = json.dumps({"checks": checks})
    return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]})


def test_decide_mirrors_the_app_policy():
    mandatory = {"task_completion", "visibility", "large_towel"}
    passing = {k: check("pass") for k in mandatory}
    assert evaluation.decide(passing, mandatory) == "pay"
    assert evaluation.decide({**passing, "large_towel": check("fail", 95)}, mandatory) == "reject"
    assert evaluation.decide({**passing, "large_towel": check("pass", 79)}, mandatory) == "uncertain"
    assert evaluation.decide({**passing, "large_towel": check("fail", 50)}, mandatory) == "uncertain"


@pytest.mark.skipif(not media_executable("ffmpeg"), reason="FFmpeg required")
def test_eval_scores_clips_against_labels(tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir()
    for name in ("good.mp4", "bad.mp4"):
        subprocess.run([media_executable("ffmpeg"), "-v", "error", "-nostdin", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=15",
                        "-t", "12", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clips / name)], check=True, timeout=60)
    (clips / "labels.csv").write_text(
        "file,task_completion,visibility,large_towel,dark_surface,task_tags\n"
        "good.mp4,pass,pass,pass,fail,large_towel\n"
        "bad.mp4,fail,pass,pass,pass,\n"
        "missing.mp4,pass,pass,pass,pass,\n")
    keys = ["task_completion", "visibility", "large_towel", "dark_surface"]
    replies = [
        {k: check("pass") for k in keys} | {"dark_surface": check("fail", 85)},   # good: pay
        {k: check("pass") for k in keys} | {"task_completion": check("fail", 95)},  # bad: reject
    ]
    calls = []

    def handler(request):
        calls.append(json.loads(request.content))
        return gemini_reply(replies[len(calls) - 1])

    adapter = GeminiFrames("test-key", "fake-model", transport=httpx.MockTransport(handler))
    out = tmp_path / "out"
    assert evaluation.main(["--clips", str(clips), "--labels", str(clips / "labels.csv"),
                            "--sleep", "0", "--out", str(out)], adapter=adapter) == 0
    summary = json.loads((out / "results.json").read_text())["summary"]
    assert summary["scored"] == 2 and summary["errors"] == 1
    assert summary["correct"] == 2 and summary["false_pay"] == 0
    # Frames really went to the (fake) model: 5 samples + labels per request.
    images = [p for p in calls[0]["contents"][0]["parts"] if "inlineData" in p]
    assert len(images) == 5
    assert "False pay" in (out / "report.md").read_text(encoding="utf-8")
