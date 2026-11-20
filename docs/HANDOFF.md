# FrameBounty: Full Session Handoff (for a new assistant)
*Written Thu Nov 19, 2026 (evening, US Central) by the previous assistant session. Read all of it before acting.*

> **November 20 camera update:** This is historical context. For current restart
> instructions read `..\CODEX-SESSION-HANDOFF.md` and
> `docs/plans/2026-11-20-in-app-camera.md`. The active branch is
> `feat/in-app-camera`. Video contributors now record 10–30 seconds inside the app;
> there is no video-file picker. Remote camera use requires HTTPS. Deployment and
> `main` remain out of scope for this branch.

---

## 0. TL;DR
- **User:** Ayaan Ameen (Purdue, B.S. AI, class of 2028; GitHub `Ayaan-Ameen07`). Teammate and repo owner **Rithvik** (`RithvikReddySiddenki`). Team of 4; the other two are referred to as "Teammate 3" and "Teammate 4". People may double up on tasks.
- **Event:** University Blockchain Conference (UBC) 2026 hackathon at UT Austin. **Submission due Fri Nov 20, 2026, 12:00 PM CST (team target 10:00 AM).** Finals Sat Nov 21 in Austin: in-person attendance at the closing ceremony is **required to win any prize**.
- **Project:** **FrameBounty**, an AI-managed marketplace for custom data collection. Labs (buyers) commission data via an AI buyer agent; contributors find tasks via an AI work agent; Gemini verifies uploads; USDC escrow on **Arc testnet** pays verified work. Tracks: **Agentic Payments & AI** + **Best use of Arc**.
- **Repo:** https://github.com/RithvikReddySiddenki/framebounty. All real code is on branch **`feat/framebounty-prototype`** (`main` only has a README). This session pushed `ux-fixes`, `gemini-eval` and `integration` (see §4).
- **Biggest remaining P0s:**
  1. **Live funded run on Arc testnet has never been done.**
  2. **Merge everything to `main`.**
  3. **Judge README** (draft exists).
  4. **Demo video** + **Devpost** by 10 AM Fri.
  5. Finish/review the `integration` WIP (T1 runbook incomplete).

---

## 1. Hackathon rules (from the official "Hackathon Guide UBC 26" PDF)
- Hacking started **Thu Nov 12, 6 PM CST** (ignore Devpost's Friday start). Deadline **Fri Nov 20, 12 PM CST**. Finalists notified by Nov 20, 11:59 PM CST. Judging and finals Sat Nov 21.
- **No pre-existing projects**: the work must be substantially built during the hackathon. Commits on the repo start Nov 16, which is fine. **AI tools are encouraged.** Teams of 1–4.
- **Pick exactly 1 main track**, **1 optional chain award** (Solana $1,500/track or **Arc $1,000/track**, never both), and any bounties. Track winner $2,000. Overall 1st $2,500 (+ElevenLabs Pro), 2nd $1,000, 3rd $500. All prizes stack except Solana/Arc together.
- **Finalists: up to 13.** Per track: the top track contender, the top Solana project and the top Arc project; plus the top 3 overall and the Gemini bounty 1st place. **Choosing Arc means competing only against other Arc projects in the track.** Pitch is 5 min + 2 min Q&A.
- **Agentic Payments & AI track requirements:**
  - Agents execute onchain transactions or read the chain (testnet is fine).
  - **The README must document the agent's decision loop and the safety limits.**
  - Recommended tools: x402, Circle Agent Wallets/Nanopayments, Solana Agent Kit.
- **Best use of Arc:** core onchain functionality on Arc (testnet is fine); the README must include the contract address(es) and how Arc is used. Combining with Circle tools is encouraged.
- **Bounties (optional):**
  - **Gemini Prediction Markets:** uses Gemini's prediction-market API. This is Gemini *the exchange*, not Google Gemini AI; we are not using it.
  - **ElevenLabs:** voice must be central.
  - **QuickNode Streams:** at least one Stream with a filter and a destination, explained in the README.
  - **Grok Bot on X:** needs a chat export.
  - Not pursued.
- **What to submit (Devpost):**
  - Project name, description and team.
  - The track, chain award and bounties.
  - Written answers: what you built, the problem, how it works, what makes it unique, what's next.
  - Tech used.
  - **A public GitHub repo of code built during the hackathon** with setup instructions.
  - **A working demo or deployed app.**
  - **A 2–3 min demo video** (YouTube/Drive, public).
  - A README with technical docs and architecture.
  - Track-specific items (contract address, decision loop, safety limits).
- **Judging criteria:** technical execution, product & UX, innovation, impact & potential, demo.

---

## 2. Product as built (Rithvik's code; reviewed and tested this session)
**Stack:**
- `apps/web`: Next.js 16 / React 19, one page with Buyer and Contributor workspaces. Uses raw `window.ethereum` (MetaMask); no wagmi.
- `services/api`: FastAPI + SQLAlchemy + Alembic + **PostgreSQL** (SQLite rejected), migrations 0001–0008.
- `contracts`: Solidity 0.8.24 `FrameBountyEscrow.sol`, built with Arc Foundry.
- `scripts/`: setup, deploy, tests.
- Docs live in `docs/`: architecture, state-machine, decisions 0001–0012, live-validation, test-matrix, workboard, and PROJECT_BRIEF (the Codex master prompt Rithvik used).

**Flow:**
1. Buyer signs in with MetaMask on Arc testnet (signed challenge, 8 h session).
2. Buyer chats with the **buyer agent** (Gemini), which asks for missing count, budget and media type, then drafts a plan (≤20 items, reward = floor(budget/count), requirements, rights).
3. Buyer publishes: MetaMask signs `createProtectedJob` → USDC `approve` → `deposit`. The first batch is 2 slots.
4. Contributor (a **different wallet**; self-trade is blocked) chats with the **work agent**, which ranks real funded listings. The contributor reserves with a two-step click, and the backend **allocator key** calls `reserve` on chain.
5. For video work, the contributor opens the in-app camera, records/reviews 10–30 s, and submits browser MP4/WebM; there is no existing-video picker. Image work retains JPEG/PNG selection. The contributor then signs `submit(sha256)` in their own wallet (needs gas).
6. The **media worker** probes and decodes with ffmpeg, samples **5 frames** (0, ¼, ½, ¾, end−250 ms; 640 px), and calls Gemini `assess_post` with a JSON schema. Each check returns {pass/fail/uncertain, confidence 0–100, explanation, timestamps}.
7. A **deterministic policy** (`automatic_verification.py`, THRESHOLD=80) decides; mandatory checks are task_completion, visibility and the task's tags:
   - all pass ≥80 → verified
   - any fail ≥80 → rejected, with reasons
   - otherwise retry ×3, then every 5 min; never paid
8. The **chain worker** (allocator/oracle key) calls `verify(id, evidenceHash)`, which sets `payAfter = now + 1h`. Anyone can `settle` after that, and the keeper does. The buyer can pay early with `approveBatch` (≤20 items, atomic). **The buyer can't veto verified work.** Rejections go through `rejectVerification`.
9. After each confirmed payout, the deterministic **next batch** publishes ≤2 slots for the missing categories.
10. **Extras:**
    - Watermarked 480 px previews until payment; originals after.
    - On-chain ±1 ratings per paid trade.
    - Refund of uncommitted funds after expiry.
    - ZIP + manifest export.

**Safety:**
- The LLM never moves money.
- Allow-listed tools: buyer `draft_plan/inspect_job/next_batch`; contributor `search_tasks/read_task/prepare_confirmation/reserve_task/my_work`.
- Every transaction's destination and function selector are validated, and receipts are matched against expected events.
- Transaction intents are durable.

**Arc facts (verified from the docs):**

| Item | Value |
|---|---|
| Chain ID | 5042002 (`0x4cef52`) |
| RPC | `https://rpc.testnet.arc.io` |
| Explorer | `https://explorer.testnet.arc.io` |
| Faucet | `https://faucet.circle.com` |
| **USDC ERC-20** | `0x3600000000000000000000000000000000000000`, **6 decimals** |
| Native gas | USDC, **18 decimals** (the same balance) |
| Fee floor | `maxFeePerGas` ≥ 20 gwei, or the tx is silently dropped |

**Escrows on Arc testnet:**

| Version | Address | Status |
|---|---|---|
| **V3 (current)** | **`0xe613799458201e41830a5be3da5c2a7d18140da0`** | Deploy tx `0x5fa53fe2a9d61756daada30a42dcf9d5361682f73c8a03c6a2c23f6f7cc0477b`; this session confirmed the bytecode is on chain |
| V2 | `0xea83a29db7486295b93318081447222481d0dbea` | Older jobs only |
| V1 | `0xd99355572a0a93f97254af3715300082fca3b063` | Older jobs only |

**Not in the build:** Circle SDKs, wallets, Gateway or x402 (only USDC on Arc). Pitch Circle email wallets as "next".

**Env flags (all safe-off by default):**
- `APP_MODE` = fixture | testnet
- `ALLOW_CHAIN_TRANSACTIONS`, `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING`
- `ALLOW_MODEL_TEXT`, `ALLOW_MODEL_MEDIA`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `ARC_RPC_URL`, `ARC_ESCROW_ADDRESS`, `ARC_ALLOCATOR_ADDRESS`, `ARC_ALLOCATOR_PRIVATE_KEY`
- `FIXTURE_VERIFICATION_RESULT`, `STORAGE_ROOT`, `DATABASE_URL`, `AUTH_ORIGIN`, `NEXT_PUBLIC_API_URL`

The API does **not** auto-load `.env`; use `scripts/load-env.ps1`.

---

## 3. Team decisions to respect
- **No consent checkbox on upload** (decision 0011; e2e asserts zero checkboxes). Clicking Submit with the visible notice is the consent. **The user confirmed: "keep it as is."**
- **Keep Rithvik's design:** Gemini (not Claude), MetaMask (not Circle wallets), the 1-hour payment window with buyer early release, both agents, rule-based rebalancing.
- **Never push to Rithvik's `feat/framebounty-prototype` or to `main` without the user explicitly asking.** Use new branches.
- **Verification must be general,** not towel-only (the user stressed this): it should work for most simple movements. The verifier uses each post's own title and requirements.
- **Order: make it work first, styling ("glamifying") later.**
- **Never print or commit secrets.** The Gemini key is stored in the **Windows user environment variable `GEMINI_API_KEY`** (HKCU\Environment). Read it via `winreg`; never echo it.

---

## 4. Git state (all pushed to origin as of this handoff)
| Branch | Head | Contents | Status |
|---|---|---|---|
| `feat/framebounty-prototype` | `b86fd8d` | Rithvik's whole app (27 commits, Nov 16–19) | Untouched by us |
| `ux-fixes` | `c2215db` | MetaMask auto-add/switch to Arc testnet (`api.ts` `ensureArcTestnet`, EIP-3326/3085); copy fixes ("towel fold required" on every post → generic; footer → "Verified work is paid automatically from escrow"); +2 unit tests | **CI green** (api, web, contracts) |
| `gemini-eval` | `bd8fd5c` | `scripts/eval_verification.py` (offline accuracy test, task-agnostic) + `services/api/tests/test_eval_verification.py` | Pushed, on top of ux-fixes |
| `integration` | **WIP commit (this handoff)** | Everything above, plus the T1/T2/T3 work-in-progress (§6) and this file at `docs/HANDOFF.md` | **Not fully reviewed**; T1 incomplete |

Suggested merge path, once the team agrees: `integration` → PR into `feat/framebounty-prototype` (or straight to `main`) → merge to `main` so judges see the code. Rithvik should approve.

---

## 5. Verified test results (run on Ayaan's laptop this session)
| Suite | Result |
|---|---|
| Backend pytest with real Postgres | **162 passed**, 0 failed (22 chain-gated skips, which run in test_chain) at Rithvik's head; later 166 passed / 23 skipped with the T2 work |
| Contracts (Arc Foundry via WSL Ubuntu) | **27/27** incl. fuzz |
| Local-chain integration (`scripts/test_chain.py`) | **24/24** (~4.5 min) |
| Web typecheck / unit (`npm run test:publishing`) / build | clean / **11/11** / OK |
| Playwright e2e (`scripts/test_e2e.py`) | **8 passed, 1 skipped**, before and after all changes |
| Live Gemini, `gemini-3.5-flash-lite`, 3 real clips | **3/3 correct, 0 false pay** (after the T2 prompt change too); ~20 s per clip (mostly full 1080p decode) |
| Live Gemini, synthetic test pattern | Rejected. Visibility was "pass" before T2 and "fail" after T2 |
| Live end-to-end paid flow on Arc | **NEVER RUN** |

---

## 6. Work in progress on `integration` (subagent-driven; stopped by the user mid-way)
- **T1 – demo runbook + start script.** **INCOMPLETE.**
  - `scripts/demo.ps1` exists (284 lines; `-Mode fixture|testnet`, `-Action start|stop|status`, PIDs and logs in `.local/demo/`).
  - It **was not reviewed**, and its verification run state is unknown. **`docs/DEMO.md` was never written.**
  - The spec is in §11 below. Review or test the script before trusting it.
- **T2 – Gemini prompt fix.** Implemented and **spec review APPROVED.**
  - `services/api/framebounty/verification.py` `assess_post` instruction now defines **visibility** (hands and task objects visible, not just a sharp image; no person or out of frame → must not pass, except for non-human requests such as still images of an animal or scene) and **task_completion** (action performed AND end state visible; attempting or holding ≠ completion; if the end state isn't shown, use uncertain or fail).
  - Test: `services/api/tests/test_verification_prompt.py`.
  - The tightened parenthetical wording is applied and its assert added; targeted tests pass (12/12).
  - **Still to do:** a live recheck of the *tightened* wording (the earlier wording passed 3/3 plus the pattern), and the **quality review**.
- **T3 – frontend checks.** Implemented. Typecheck clean, 11/11 unit, build OK, e2e 8 passed / 1 skipped. **The spec review was stopped mid-way; there is no quality review yet.**
  - `upload.tsx`: "Checking your video with AI (usually under a minute)…" for queued/verifying; retry errors shown as a notice, not a red error; "Reward paid." / "Simulated reward released…" at accepted states; the "Decision:" line is de-duplicated; a payment-window note.
  - `agent-pane.tsx`, `work-chat.tsx`, `workspace.tsx`: V3-correct payment wording.
  - `e2e/collection.spec.ts`: +1 assertion for the checking message.
  - **Deleted** dead `apps/web/app/buyer-plan.tsx`.
  - Reviewer to-do: confirm "Reward paid." only appears when payment is actually confirmed (`payment_confirmed`), and that the copy is right for both legacy and V3 jobs.
  - Backend strings T3 flagged but didn't edit:
    - `automatic_verification.py:56-62`: the reason text goes stale after payment, and "payment is blocked" shows while a retry is queued.
    - `main.py:105-109`: the "Ready for release" tile counts in-progress items.
- **T4 – judge README.** Not started. Use `README-draft.md` (in this handoff folder). Fill in the live tx links, the accuracy table (3/3, and any more clips), the video link and the team.

**Process the user requested:** the `/subagent-driven-development` skill. For each task: an implementer subagent → a separate **spec-review** subagent → a separate **quality-review** subagent; iterate until approved; only then commit. The user also uses the `executing-plans` skill (batches of ~3 with checkpoints, "Ready for feedback.") and `systematic-debugging` (root cause before fixes).

---

## 7. Gemini (AI verification)
- **The key works** (validated: HTTP 200 on the models list). It's stored as **user env var `GEMINI_API_KEY`**. It's a 53-character key; never print it.
- **Models available to the key** (from the models list): `gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.1-flash-lite`, `gemini-2.5-flash`, `gemini-flash-latest`, and others.
- **Chosen: `gemini-3.5-flash-lite`.** Free tier is reportedly ~10–15 requests/min and ~500/day (third-party reports). Flash models are reportedly ~20/day free, which is too few for the demo without a paid key.
- **Usage so far:** about 12–16 requests total today.
- **Accuracy test script:** `scripts/eval_verification.py` (task-agnostic). Labels CSV columns: `file, task, requirements ("key: desc | key2: desc"), task_completion, visibility, expected ("key=pass; ..."), task_tags`. The legacy towel columns are also supported.
  - It writes `report.md` and `results.json`.
  - The key metric is **False pay**, which must be 0.
  - It mirrors the app policy (threshold 80) and validates rows as a real `Plan` before spending model calls.
- **The user's clips:** `C:\Users\ayaan\UBC video labels\` contains `fail bottle pour.MOV`, `succesful bottle pour.MOV`, `succesful towl fold.MOV` (the file name = the true label), plus `labels.csv` and `eval-report-flash-lite.md`. iPhone 1080p H.264, 12–19 s.
- **Observations:**
  - Confidence is nearly always 100 (uncalibrated).
  - Near-miss clips (pour misses the glass, half fold, hands out of frame, very quick action, a new movement) are **optional**; the user asked whether they were necessary, and the answer was no, only if time allows.
- **Helper scripts (outside the repo, in the old scratchpad, which may be deleted):** `run_eval.py` and `gemini_key_check.py`. They read the key from `winreg` and call `scripts/eval_verification.py`'s `main`. Easy to recreate:
  ```python
  import winreg, os
  os.environ["GEMINI_API_KEY"] = winreg.QueryValueEx(winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment"), "GEMINI_API_KEY")[0].strip()
  ```
  Then run `scripts/eval_verification.py --clips "<dir>" --labels "<dir>/labels.csv" --model gemini-3.5-flash-lite --sleep 7 --out <dir>`, with `services/api` on `sys.path`.

---

## 8. Local environment notes (Ayaan's Windows 11 laptop)
- **Tools:**
  - Git Bash and PowerShell 5.1; Python **3.13** (CI uses 3.12; fine); Node 22.21; WSL with an **Ubuntu** distro (used for the Arc Foundry Linux binaries).
  - **No `gh` CLI.** Git pushes work over HTTPS with stored credentials as GitHub user `Ayaan-Ameen07`.
- **Review clone used this session (TEMP scratchpad, may vanish):**
  `C:\Users\ayaan\AppData\Local\Temp\claude\f23774a542bdb16c\ab5aaad8-d1cf-4617-9ed3-7a8899cdffb3\scratchpad\repo-review\framebounty`
  It has `.venv` (deps installed), `.local/ffmpeg` (portable FFmpeg), `.local/arc-foundry` (forge/anvil/cast/solc via WSL), `.local/browsers` (Playwright Chromium) and `apps/web/node_modules`. **A new assistant should clone fresh** from GitHub (branch `integration`) into a persistent folder and re-run the setup.
- **Database:** **Docker Desktop is broken.** Root cause: the corrupted stale socket `%LOCALAPPDATA%\Docker\run\dockerInference` (Windows error 1920) crashes the backend at startup every time. Fix if wanted: quit Docker, rename `%LOCALAPPDATA%\Docker\run` → `run.broken`, restart. The user said to leave it for now.
- **Instead: portable PostgreSQL 16.10** at `...\scratchpad\pg-portable\pgsql`, data dir `...\scratchpad\pg-portable\data`, **port 55433**, user/password `framebounty`/`framebounty`, database `framebounty_test`.
  - Start it with `pg_ctl.exe -D data -o "-p 55433 -h 127.0.0.1" -l pg.log start` (run it in the background: in Git Bash `pg_ctl -w` holds the pipe).
  - Stop it with `pg_ctl.exe -D data -m fast stop`. **It may still be running now.**
  - The download is `https://get.enterprisedb.com/postgresql/postgresql-16.10-1-windows-x64-binaries.zip`. Extract bin/lib/share fully: partial extraction broke initdb because `share/timezonesets` was missing.
- **How each suite runs:**
  - Backend: `TEST_DATABASE_URL=postgresql+psycopg://framebounty:framebounty@127.0.0.1:55433/framebounty_test .venv/Scripts/python.exe -m pytest services/api/tests -q -p no:cacheprovider --basetemp=.local/pytest-X`
  - Contracts: `npm ci --prefix contracts`; `python scripts/setup_arc_tools.py`; then in WSL `forge test --root <wsl path>/contracts --use <wsl path>/.local/arc-foundry/solc-0.8.24 --offline`
  - Local chain: `TEST_DATABASE_URL=... python scripts/test_chain.py`
  - E2E: `PLAYWRIGHT_BROWSERS_PATH=.local/browsers npm exec --prefix apps/web -- playwright install chromium`; then `TEST_DATABASE_URL=... python scripts/test_e2e.py` (uses ports 3002/8002)
  - Web: `cd apps/web; npm run typecheck; npm run test:publishing; npm run build`. Run `git checkout -- apps/web/next-env.d.ts` after a build.
- **Skills auto-sync:** the user's skills live in `C:\Users\ayaan\OneDrive\Documents\Claude\Skills\` (brainstorm, execution, systematic debugging, finishing a development branch, sub agent parralelization). They're installed to `~/.claude/skills/<name>/SKILL.md`. A **SessionStart hook** in `~/.claude/settings.json` runs `~/.claude/scripts/sync-skills.sh` (copy-only, never deletes).

---

## 9. Remaining work (prioritized)
| Pri | Item | Owner (suggested) | Notes |
|---|---|---|---|
| **P0** | **Live funded run on Arc testnet**, clicking through BOTH workspaces in live mode | Rithvik + Ayaan | Needs 3 wallets: buyer (budget + gas), contributor (gas for submit; must differ from buyer), allocator (`scripts/setup_local_allocator.py` makes one; fund it from the faucet). Testnet env flags (§2), `GEMINI_MODEL=gemini-3.5-flash-lite`. Run Postgres, API, media worker, chain worker and web (built with funding enabled). Use **buyer early release** to avoid the 1-hour wait. **Record tx links** for the README. The live UI has never been seen (screenshots are fixture-mode only). |
| **P0** | Finish `integration`: T1 (`DEMO.md` + review the script), T2 quality review + live recheck, T3 spec + quality review; then commit | Assistant | Follow the subagent-driven-development process |
| **P0** | **Merge to `main`** (via PR; Rithvik approves) | Rithvik | Judges see the default branch |
| **P0** | **README** on `main` from `README-draft.md` | Teammate 3 | Fill in tx links, accuracy (3/3, 0 false pay), video link, team. Must include the decision loop, safety limits, escrow address and Arc usage |
| **P0** | **Demo video 2–3 min** + **Devpost** (Agentic track + Best use of Arc) by **10 AM Fri** | Teammates 3/4 | Script in the PRD §11 |
| P1 | Two-wallet demo setup (two browser profiles or laptop + phone); phone upload over Wi-Fi (`AUTH_ORIGIN`/`NEXT_PUBLIC_API_URL` = LAN IP) | Teammate 4 | |
| P1 | Pitch deck + rehearsal (5 min + 2 min Q&A); travel to Austin for Nov 21 | Team | |
| P2 | Optional near-miss clips for accuracy; Docker fix; public hosting; backend string fixes flagged by T3 | — | Only if time allows |
| Later | "Glamifying" the UI | — | The user said: function first, styling later |

**Demo storyline (5 min):**
1. Buyer chat → plan → MetaMask publish (escrow on the explorer).
2. Contributor chat → reserve → upload a pre-filmed clip → sign submit.
3. AI checks per criterion with reasons; show one rejected clip.
4. Buyer early release → USDC lands (explorer link).
5. Coverage gap → next batch auto-commissioned → ratings.
6. Close on: the AI never touches money; contract limits; trust assumptions (the oracle key and the AI are centralized).

---

## 10. Files in this handoff folder (copied from the session; also see the repo)
| File | What it is |
|---|---|
| `HANDOFF.md` | This file (also at `docs/HANDOFF.md` on the `integration` branch) |
| `FrameBounty-PRD.md` | **PRD v3**, matching the build: flows, verification policy, contract functions, safety limits, demo script, Q&A |
| `framebounty-repo-review.md` | Deep review of Rithvik's code; verified vs unproven; differences from earlier plans |
| `framebounty-diagnostic.md` | Test diagnostic + rationale for the ux-fixes changes; Docker root cause |
| `framebounty-worklist.md` | Work list A/B/C with priorities (some items now done; §9 above is current) |
| `README-draft.md` | Judge-facing README draft with placeholders |
| `gemini-setup-guide.md` | How Gemini is used, model choice, shot list, labels format |
| `UBC-2026-prep.md` | Early prep guide incl. the official-rules summary (older parts superseded) |
| `ideas-shelf.md`, `Groundtruth-PRD.md`, `robotics-data-deep-dive.md`, `office-hours-nov16.md` | Earlier ideation history (superseded by FrameBounty) |
| `framebounty-ux-fixes.patch` | The ux-fixes diff (already pushed as a branch) |

---

## 11. T1 spec (to finish)
- **`docs/DEMO.md`**, a runbook covering:
  - prerequisites: venv, Node, FFmpeg via `scripts/setup_media_tools.py`, Postgres (Docker compose or any local Postgres via `DATABASE_URL`), MetaMask
  - **fixture** vs **testnet** modes, with the exact testnet env vars (§2, verified against `.env.example` and the code)
  - wallet checklist (3 distinct wallets, Arc network details, faucet)
  - phone/LAN upload settings
  - the live walkthrough steps, and what tx links to record
  - troubleshooting: wrong chain, MetaMask nonce, Gemini 429/quota, verification uncertain/pending, worker not running
- **`scripts/demo.ps1`**:
  - start/stop/status for fixture and testnet modes
  - PowerShell 5.1 compatible (no `&&` or ternary)
  - never prints secrets
  - refuses testnet mode if required vars are missing (and lists them)
  - PIDs and logs under `.local/demo/`; stop kills only recorded PIDs
- **Verify:** start in fixture mode against Postgres, check `/health` and the web page return 200, check status, stop, and confirm nothing is left running. Testnet mode with no vars must refuse clearly.

---

## 12. Earlier session history (brief)
1. Researched UBC 2026 and its tracks, Claude skills for web3, and VC requests-for-startups (YC W27 RFS, YC crypto RFS, Coinbase Ventures, Variant, a16z).
2. Brainstormed many ideas; shelved a hedger-created prediction market and self-repaying machine loans.
3. Chose robotics training data ("Groundtruth"), which evolved into the team's **FrameBounty** proposal.
4. Wrote PRDs v1–v3. Office hours with Solana/Circle were on Nov 16. A Circle engineer outreach email was drafted.
5. Discovered Rithvik had already built most of the app with Codex. Reviewed it, ran every test suite, fixed small UX issues, built the Gemini accuracy test, tested the user's key and clips, and started the integration round.
6. Diagnosed the Docker failure.

---

## 13. Instructions for the next assistant
1. **Clone fresh:** `git clone https://github.com/RithvikReddySiddenki/framebounty.git && git checkout integration`. Set up the venv, FFmpeg, Postgres (portable, as in §8, or fix Docker) and node_modules per the repo README.
2. Run all suites to re-baseline (§5). Expect the same numbers.
3. Finish T1/T2/T3 reviews (§6); commit; ask the user before pushing or merging anywhere other than `integration`.
4. Help with the **live Arc run**. The user signs MetaMask transactions themselves; never handle private keys except the dedicated allocator key in an ignored `.env`. Then fill in the README and help with the video and Devpost.
5. Mind the deadline: **Fri Nov 20, 10 AM CST target, 12 PM hard.**
