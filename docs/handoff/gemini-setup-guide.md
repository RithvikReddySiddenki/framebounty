# Gemini Setup and Accuracy Test: Guide (owner: Ayaan)

## How Gemini is used in FrameBounty (already built by Rithvik)
One adapter, `GeminiFrames` (`services/api/framebounty/verification.py`), calls the Gemini REST API with a **JSON schema**, so the answer is always structured. There's **no hardcoded model**: it's whatever `GEMINI_MODEL` says.

| Where | What Gemini does | Calls |
|---|---|---|
| **Buyer chat** (`chat.py`) | Turns "20 towel videos under 20 USDC" into a plan | ~1 per message |
| **Contributor chat** (`chat.py`) | Extracts what the contributor has, ranks real funded tasks | 1–2 per message |
| **Verification** (`worker.py` → `assess_post`) | Looks at **5 frames** (start, ¼, ½, ¾, end; 640 px JPEG) and scores every requirement: `pass/fail/uncertain` + confidence 0–100 + reason + timestamps | 1 per clip (up to 3 retries) |

**The decision is made by code, not by Gemini** (`automatic_verification.py`, threshold 80):
- All mandatory checks (`task_completion`, `visibility`, plus the task's tags such as `large_towel`) **pass at ≥80** → verified → paid after the window.
- Any mandatory check **fails at ≥80** → rejected, with Gemini's reason shown to the contributor.
- Anything else → **retry / held, never paid**.

**Safety switches (all off by default):** `ALLOW_MODEL_TEXT=true` (chat), `ALLOW_MODEL_MEDIA=true` (send frames), plus a per-upload consent flag. The key goes only in `.env` as `GEMINI_API_KEY`, never in `NEXT_PUBLIC_*`.

## Choosing the model
| Candidate | Free-tier limits (third-party reports; **check AI Studio**) | Fit |
|---|---|---|
| **`gemini-3.5-flash-lite`** | ~10–15 requests/min, **~500/day** | Default pick: enough quota for testing plus the demo. Already smoke-tested in the repo |
| `gemini-3.8-flash` / `gemini-3.6-flash` | ~5 requests/min, **~20/day** | Probably more accurate, but 20/day is too few for testing *and* demo day on the free tier |

**Recommendation:** run the accuracy test on **flash-lite first**. If it makes mistakes on `task_completion` or the towel/surface checks, run the same clips on a Flash model and compare. If the better model wins, use a **paid key** (cheap at this volume) so demo day can't hit the 20/day cap.
**Privacy:** check Google's terms for free-tier data use before sending real contributor videos. Only send clips your team filmed.

## The work list
1. **Get a key.** Create a Gemini API key in Google AI Studio. Confirm which models your key can use:
   ```bash
   curl -s "https://generativelanguage.googleapis.com/v1beta/models" -H "x-goog-api-key: $GEMINI_API_KEY" | grep '"name"'
   ```
2. **Film 12–20 clips** (10–30 s each, phone propped up, MP4 or MOV). Use the shot list below.
3. **Label them** in `labels.csv` (template below).
4. **Run the accuracy test** (new script, tested offline):
   ```powershell
   $env:GEMINI_API_KEY="..."   # don't commit it
   .\.venv\Scripts\python.exe scripts/eval_verification.py --clips clips --labels clips/labels.csv --model gemini-3.5-flash-lite
   ```
   It writes `.local/eval/report.md` (table plus summary) and `results.json`.
5. **Read the report. The key number is "False pay"** (bad work that would get paid), which must be **0**. Then check false rejects and uncertain counts.
6. **Tune** the requirement descriptions if one check keeps failing (e.g. make "dark surface" more concrete), then re-run. Try a second model if needed.
7. **Lock it in:** set `GEMINI_MODEL`, `ALLOW_MODEL_TEXT=true`, `ALLOW_MODEL_MEDIA=true` in the demo `.env`. Give Rithvik the model name for the live run, and give Teammate 3 the report table for the README.

## Shot list (aim for ~16 clips)
| # | Clip | Expected |
|---|---|---|
| 1–4 | Complete fold, **large towel on dark table** | pay (counts for both tags) |
| 5–6 | Complete fold, **large towel on light surface** | pay for the large-towel task; reject for the dark-surface task |
| 7–8 | Complete fold, **small towel (hand towel) on dark table** | pay for dark; reject for large |
| 9–10 | Complete fold, small towel, light surface | pay for a general task only |
| 11–12 | **Starts folding but stops halfway** | reject (`task_completion` fail) |
| 13 | Hands mostly **out of frame** | reject or uncertain (`visibility`) |
| 14 | **Wrong task** (e.g. folding a shirt) | reject |
| 15 | Very dark / blurry video | reject or uncertain |
| 16 | 8-second clip (too short) | error: duration out of range (the decoder rejects it, not Gemini) |

## `labels.csv` template
```csv
file,task_completion,visibility,large_towel,dark_surface,task_tags
clip01.mp4,pass,pass,pass,pass,large_towel;dark_surface
clip05.mp4,pass,pass,pass,fail,large_towel
clip07.mp4,pass,pass,fail,pass,dark_surface
clip11.mp4,fail,pass,pass,pass,
clip13.mp4,pass,fail,pass,pass,
```
- `task_tags` is what the reserved task requires. Leave it empty for a general task.
- The test computes the expected decision as **pay only if every mandatory check is "pass"**.

## Budget for demo day (calls)
- Accuracy runs: ~16 clips × 2–3 runs ≈ 50 calls.
- Live demo: ~10 chat messages (~15 calls) + ~5 clips (≤15 calls with retries) ≈ 30 calls.
- On flash-lite free (~500/day) that's fine. On Flash free (~20/day) it **won't** fit, so use a paid key.
