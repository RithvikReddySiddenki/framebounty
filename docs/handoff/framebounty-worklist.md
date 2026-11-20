# FrameBounty Work List
*Thu Nov 19, 2026 · deadline **Fri Nov 20, 12:00 PM CST** (target 10 AM) · finals Sat Nov 21 in Austin (attendance required)*

**Code state:** `feat/framebounty-prototype` @ `b86fd8d` (Rithvik) + `ux-fixes` @ `c2215db` (pushed Nov 19: MetaMask auto-adds Arc, copy fixes, 2 tests). `main` still has only the README.

**Verified working locally:** backend 162 ✅ · contracts 27 ✅ · local-chain 24 ✅ · browser end-to-end 8 ✅ · web typecheck, 11 unit tests, build ✅ · V3 escrow live on Arc ✅

---

## A. Not working or never proven
| # | Item | Pri | What "done" means | Suggested owner |
|---|---|---|---|---|
| A1 | **Live funded run on Arc testnet has never happened** (fund → reserve → submit → AI verify → pay) | **P0** | One full run with real testnet USDC; transaction links for funding, reserve, verify and payout recorded in the README | Rithvik (with Ayaan) |
| A2 | **Gemini not configured for real use**: `GEMINI_MODEL` unset, `ALLOW_MODEL_TEXT/MEDIA` off; the only call so far was a synthetic smoke test | **P0** | Model chosen, `.env` set, buyer chat and verification working with live Gemini | Ayaan |
| A3 | **AI accuracy on real towel videos never measured** | **P0** | 10–20 real clips (passes, fails, large/dark variants) run through the verifier; accuracy and latency table in the README | Ayaan |
| A4 | **Phone upload never tested** (the README says phone/LAN testing is pending) | P1 | Upload from a phone to the laptop's demo over Wi-Fi works; `AUTH_ORIGIN` / `NEXT_PUBLIC_API_URL` set for the LAN address | Teammate 4 |
| A5 | **One-hour wait before automatic payment** makes the "money lands" moment slow on stage | P1 | Demo script uses the buyer's **early batch release** (already built); rehearsed once | Teammate 4 |
| A6 | Docker Desktop crashes on start on Ayaan's laptop (corrupted socket file) | P2 | Only if needed: rename `%LOCALAPPDATA%\Docker\run` to `run.broken`. Portable Postgres works without it | Ayaan |
| A7 | Known gaps in Rithvik's notes: wallet fee replacement, automatic recovery when a transaction hash is lost, cancelling unsigned pending allocations, untested container runtime | P2 | Not needed for the demo; list under "Next" in the README | n/a |

## B. Needs to be built or done for submission
| # | Item | Pri | What "done" means | Suggested owner |
|---|---|---|---|---|
| B1 | **Merge to `main`**: `feat/framebounty-prototype` + `ux-fixes` (judges see the default branch) | **P0** | PR(s) merged, CI green on `main` | Rithvik |
| B2 | **Judge-facing README** (draft ready: `README-draft.md`) with the A1 transaction links and A3 accuracy filled in | **P0** | README on `main` with decision loop, safety limits, escrow address, how Arc is used, results | Teammate 3 |
| B3 | **Demo runbook / start script**: one command or checklist that starts Postgres, API, media worker, chain worker and web with the testnet settings, plus pre-funded wallets | P1 | Anyone on the team can bring the live demo up in under 5 minutes | Rithvik or Ayaan (I can build this) |
| B4 | **Demo video (2–3 min)** following the PRD's demo script | **P0** | Public YouTube/Drive link in Devpost and the README | Teammate 4 |
| B5 | **Devpost submission**: Agentic track, Best use of Arc; answers to what / problem / how / unique / next | **P0** | Submitted by **10 AM Fri** | Teammate 3 |
| B6 | **Pitch deck / 5-minute talk + 2-minute Q&A prep** (finals) | P1 | Slides plus rehearsed demo, using the PRD's Q&A answers | Whole team |
| B7 | Confirm GitHub Actions passes on `ux-fixes` | P1 | Green check on the branch / PR | Ayaan (I can check) |
| B8 | Clean-ups: remove dead `buyer-plan.tsx`; the old towel/cat-only fixture planner | P2 | Removed, tests still pass | Anyone |
| B9 | Public hosting of the demo | P2 | Only if time allows; otherwise demo from a laptop | n/a |

## Status update (Thu evening)
- **A2 done:** the Gemini key works; **`gemini-3.5-flash-lite`** chosen.
- **A3 started:** 3/3 real clips correct (pour, failed pour, towel), 0 false pays, ~20 s per clip. Every answer was at 100% confidence, so 2 near-miss clips are optional if there's time.
- **Branches pushed:** `ux-fixes` (CI green), `gemini-eval` (task-agnostic accuracy test).

## C. Frontend: both user types (labs and contributors)
**Already built** by Rithvik (Next.js) and checked with real screenshots from the browser tests:
- **Sign-in page:** wallet sign-in, FrameBounty branding, Arc testnet notice.
- **Lab (buyer) workspace:** overview stats (collections, open, ready for release); **buyer agent chat** that asks for missing details and builds a plan preview (items, reward, budget, requirements, usage rights, payment-window terms); publish / save draft; **Collections & review** with AI checks per submission, watermarked previews, coverage, "Commission next batch", early funds release, refund, export, ratings.
- **Contributor workspace** (works on phone width): **work agent chat** that finds funded tasks and shows a reward card → review → reserve; **My submissions** with upload, status, AI verification results per check, and payment state.

| # | Frontend item | Pri | What "done" means | Suggested owner |
|---|---|---|---|---|
| C1 | **Live (testnet) mode never seen in the browser.** Screenshots are fixture mode; the funding steps (create → approve → deposit in MetaMask), contributor `submit` signature and real payout states only show when the web app is built with `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true` | **P0** (part of A1) | Click through both workspaces in live mode during the A1 run; note anything confusing | Rithvik + Ayaan |
| C2 | **Two-user demo setup:** lab and contributor need different wallets, so use two browsers or profiles (or laptop + phone) | P1 | Both signed in side by side before the demo starts | Teammate 4 |
| C3 | **Verification wait (~20 s per clip) on screen:** check that the contributor sees a clear "checking…" state and that status updates without confusion | P1 | Rehearsed; tweak copy if it looks stuck | Ayaan |
| C4 | Fixture-only copy says "awaiting buyer funds release" (old flow); confirm live V3 shows the payment-window wording instead | P2 | Verified in C1 | n/a |
| C5 | Phone upload over Wi-Fi (same as A4) | P1 | Contributor uploads a real clip from a phone | Teammate 4 |

## Suggested order (now → Fri 10 AM)
1. **B1** merge, and start **A2** in parallel (model choice and keys).
2. **A1** live run, then **A3** clips and accuracy. *(Both can use the same live setup; B3 makes it repeatable.)*
3. **B2** README → **B4** video → **B5** Devpost. **Freeze 9 PM Thursday.**
4. **B6** pitch rehearsal Friday morning or on the trip.
