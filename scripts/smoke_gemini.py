"""One explicit free-tier smoke using generated cards, never private task media.

This verifies transport/schema behavior, not task-quality accuracy. It does not
enable application inference or approve quality/payment.
"""
import io
import json
import os
import time
from pathlib import Path

from PIL import Image, ImageDraw

from framebounty.verification import GeminiFrames, ProviderFailure


def main():
    if os.getenv("ALLOW_LIVE_MODEL_SMOKE") != "true" or os.getenv("GEMINI_FREE_TIER_CONFIRMED") != "true":
        raise SystemExit("Confirm the project is free-tier with billing disabled and explicitly enable this smoke first")
    image = Image.new("RGB", (640, 360), "#54566b")
    ImageDraw.Draw(image).text((20, 20), "SYNTHETIC SMOKE TEST: no person, towel or task demonstration", fill="white")
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=75)
    frames = [(stamp, output.getvalue()) for stamp in (0, 6000, 12000)]
    started = time.monotonic()
    try:
        adapter = GeminiFrames(os.getenv("GEMINI_API_KEY", ""), os.getenv("GEMINI_MODEL", ""))
        assessment = adapter.assess(frames, "Synthetic color cards only. No physical task or towel is demonstrated. Do not infer physical dimensions or claim useful collected data.", 12000)
    except ProviderFailure:
        raise SystemExit("Live Gemini smoke failed; application model flags remain unchanged") from None
    if assessment.task_completion.result == "pass":
        raise SystemExit("Model falsely passed synthetic non-task cards; keep live model flags disabled")
    result = {"model": adapter.model, "synthetic_input_only": True, "schema_valid": True,
        "latency_seconds": round(time.monotonic() - started, 3), "assessment": assessment.model_dump(),
        "limitations": "One synthetic negative smoke; not a physical-task accuracy/latency benchmark or quality approval."}
    path = Path(__file__).resolve().parents[1] / ".local/gemini-smoke.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "assessment"}, indent=2))


if __name__ == "__main__":
    main()
