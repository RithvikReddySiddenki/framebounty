# FrameBounty: Product Requirements Document (v3, matches the build)
*An AI-managed marketplace for custom data collection. Robotics demonstration video is the launch use case.*

| | |
|---|---|
| **Event** | UBC 2026 Hackathon. Submit by **Fri Nov 20, 12:00 PM CST** (target 10 AM). Finals Sat Nov 21 in Austin (in-person attendance required to win). |
| **Main track** | Agentic Payments & AI |
| **Chain award** | Best use of Arc |
| **Repo** | `github.com/RithvikReddySiddenki/framebounty`, branch `feat/framebounty-prototype` (**merge to `main` before submitting**) |
| **Escrow (V3, Arc testnet)** | `0xe613799458201e41830a5be3da5c2a7d18140da0` |
| **Status** | PRD v3, Thu Nov 19. **Describes what is built.** Replaces v2, which assumed Claude, Circle email wallets and a moderator. Items marked ⚠️ are built but not yet proven live. |

---

## 1. Summary

### One-liner
A lab describes the data it needs to an AI buyer agent. FrameBounty turns the request into a funded USDC escrow on Arc, contributor agents help people find and reserve tasks, AI verifies every clip against the agreed rubric, and verified work is paid out automatically. The system then commissions whatever examples are still missing.

### 30-second pitch
> "Robotics labs need specific demonstration videos ('20 towel folds, at least 5 with large towels and 5 on dark surfaces'), and today that means contractors, spreadsheets and manual review. With FrameBounty, the lab tells our buyer agent what it needs and the budget. The agent drafts a plan, and the lab locks the budget in an escrow on Arc with one MetaMask flow. Contributors tell their own agent what they have at home, and it finds matching paid tasks. Every upload is checked by Gemini against the rubric. Verified clips are paid in USDC automatically, and the buyer can't veto verified work. As data comes in, the system sees which categories are missing and commissions exactly those. The AI never touches money: payments only happen through wallet signatures or contract rules."

### Why it's agentic (track fit)
- **Two role-scoped agents:** a **buyer agent** (plan, inspect coverage, commission the next batch) and a **contributor agent** (search, rank, explain and reserve tasks with confirmation).
- **An autonomous loop:** the system observes submissions and coverage, verifies with AI, attests on chain, settles payment, and commissions the missing categories after each payout, all within limits enforced by code and by the contract.
- **The safety boundary is explicit:** the LLM can only call allow-listed tools and **cannot move funds or approve quality on its own authority.** Money moves only through user wallet signatures or deterministic rules enforced by the contract.

---

## 2. Problem
1. Commissioning **specific** training data (object sizes, surfaces, conditions) is slow and manual.
2. **Review is the bottleneck:** someone has to check every clip against the requirements.
3. **Coverage drifts:** contributors film the easiest variant, so the budget runs out before the gaps are filled.
4. **Trust on both sides:** contributors fear non-payment after doing work; buyers fear paying for bad data.

---

## 3. Roles
| Role | How they act | Signs with |
|---|---|---|
| **Buyer (lab)** | Chats with the buyer agent, publishes and funds, can release payment early, refunds unused budget after expiry, rates contributors, exports data | Own MetaMask wallet |
| **Contributor** | Chats with the contributor agent, reserves a task, uploads media, submits the content hash, rates the buyer | Own MetaMask wallet (**a different wallet from the buyer**; self-trade is blocked) |
| **Buyer agent** (Gemini) | Clarifies the request, drafts the plan, inspects coverage, commissions the next batch | No keys |
| **Contributor agent** (Gemini) | Extracts what the contributor has, searches and ranks **real funded** listings, prepares the reservation confirmation | No keys |
| **Verifier** (media worker + Gemini) | Decodes media, samples frames, scores each criterion, applies the policy | No keys |
| **Allocator / oracle** (backend key) | Records reservations, attests verified work, settles after the window, rejects confident failures, releases expired slots | `ARC_ALLOCATOR_PRIVATE_KEY` (dedicated; can't be the buyer or reviewer) |

---

## 4. Scope

### Built
- Wallet sign-in (signed challenge, 8-hour session, Arc testnet required).
- Buyer chat → plan → **one publishing flow** (create protected job → USDC approve → deposit).
- Image **and** video posts (images: JPEG/PNG ≤ 20 MiB; videos: MP4/MOV 10–30 s ≤ 100 MiB).
- Contributor chat → ranked real listings → two-step reservation.
- Private upload → contributor `submit(contentHash)` → AI verification → on-chain attestation → **automatic settlement after 1 hour**, or **buyer early batch release**.
- Automatic next batch toward missing categories after each confirmed payout.
- Watermarked previews before payment (originals unlock after payment); on-chain ±1 ratings; refund after expiry; ZIP + manifest export.
- Durable transaction intents, receipt checks and crash recovery; ~116 backend tests, 27 contract tests, 9 browser end-to-end tests, CI.

### Out of scope (say "next" in the pitch)
- Circle email-login wallets / gas sponsorship (today: MetaMask).
- Human moderator queue for uncertain clips (today: retry and hold).
- Annotation and labeling jobs, voice, QuickNode, cross-chain.
- Liveness checks, deepfake or screen-recapture detection.
- Decentralized verification (today: a trusted oracle key).
- A hosted public deployment (today: local stack demoed from a laptop).

---

## 5. User flows (as built)

### 5.1 Buyer
1. Connects MetaMask on **Arc testnet** (chain `5042002`) and signs the login challenge (no payment authority).
2. **Create collection:** types e.g. *"We need 20 videos of people folding towels, at least 5 with large towels and 5 on dark surfaces, under 20 USDC."* The agent asks for anything missing (count, budget, media type) instead of guessing.
3. Reviews the **plan preview**: title, requirements, reward per item (`floor(budget / count)`), hours, rights. Light edits are allowed.
4. **Publish:** MetaMask signs `createProtectedJob` (rubric hash, expiry by default 24 h, task estimate by default 15 min), then the USDC `approve` for the exact budget, then `deposit`. Drafts stay private until funding is verified. **The first batch publishes 2 slots.**
5. **Collections & review:** submission cards with the AI checks (result, confidence, explanation, timestamps), watermarked previews, coverage metrics, **Commission next batch**, export, and the embedded buyer agent ("Inspect my coverage").
6. **Release funds early (optional):** one signature pays up to 20 verified clips (`approveBatch`). Otherwise payment settles automatically one hour after verification.
7. After expiry: **close and refund** unused budget. After payment: **rate** contributors.

### 5.2 Contributor
1. Signs in with a **different** wallet → **Contributor workspace → Find work**.
2. Tells the agent what they have: *"I have a large towel, a dark table, and 20 minutes."* The agent searches **real funded listings only** and ranks them. Cards show the reward and the buyer's reputation.
3. **Reserve:** a two-step confirmation (terms, then accept). The allocator records the reservation on chain; the deadline is ≤ 2× the task estimate and never past the listing expiry.
4. **My submissions → Upload:** the clip uploads with progress. **MetaMask signs `submit(sha256)`** (needs a little testnet USDC for gas).
5. Sees status: verifying → verified (payment window) → **paid**, or rejected with reasons. After payment, can **rate** the buyer.

### 5.3 The autonomous loop (README "agent decision loop")
```
PLAN      buyer agent drafts plan from chat → buyer reviews → buyer signs fund (fixed budget, rubric, expiry)
PUBLISH   first batch: 2 slots
SEARCH    contributor agent ranks real funded listings → contributor confirms → allocator reserve() on chain
SUBMIT    contributor uploads + signs submit(hash) → verification job queued
VERIFY    worker: decode → 5 frames → Gemini per-criterion {pass|fail|uncertain, confidence, why, timestamps}
DECIDE    policy (deterministic): all mandatory pass ≥80 → verified | any mandatory fail ≥80 → reject
          | otherwise retry (×3, then every 5 min; funds stay held, never auto-paid)
ATTEST    allocator verify(id, evidenceHash) → payAfter = now + 1h   |   rejectVerification(id, reason) frees budget
SETTLE    after payAfter anyone calls settle(id) (app keeper does) → USDC to contributor
          (buyer may pay earlier via approveBatch, ≤20 at once)
REPLAN    after each confirmed payout: compute per-category deficits (accepted + pending + open slots)
          → publish ≤2 new slots tagged with missing categories, from remaining budget
STOP      coverage met | budget exhausted | listing expiry → buyer refunds unused budget
```

---

## 6. Verification

### 6.1 Pipeline
1. **Decode and validate** (ffprobe/ffmpeg): format, duration, size. Corrupt media → deterministic rejection.
2. **Sample frames:** 5 frames at 0, ¼, ½, ¾ and end (−250 ms), scaled to 640 px. Images: one re-encoded JPEG ≤ 640 px.
3. **Duplicates:** sha256 plus a perceptual hash. **Flagged for the buyer only, never an automatic rejection.**
4. **Gemini call:** base64 JPEG frames labeled with their timestamps (1–12 frames, ≤ 8 MB), plus the post's criteria, with a JSON schema response.
5. **Policy engine** (`automatic_verification.py`, `THRESHOLD = 80`).

### 6.2 Criteria and policy
- **Mandatory:** task completion, visibility, and the reserved task's target categories (e.g. large towel, dark surface).
- **Per criterion:** `result` (pass/fail/uncertain), integer `confidence` 0–100, `explanation`, `timestamps_ms`.

| Outcome | Rule |
|---|---|
| **Verified** (goes to on-chain attestation) | Every mandatory criterion passes with confidence ≥ 80 |
| **Rejected** (reasons shown to the contributor) | Any mandatory criterion fails with confidence ≥ 80, or the media is corrupt |
| **Pending / retry** | Anything else, or a provider error. Up to 3 attempts, then every 5 minutes; funds stay committed and the clip is **never paid automatically** |

- Confidence is **model-reported, not calibrated.** We must measure real accuracy (§10).
- Only clips with explicit consent are sent to Gemini, as reduced JPEG samples (currently implied on upload; see §10).

### 6.3 Model
- **Provider: Google Gemini** via REST `generateContent` with `responseJsonSchema`. The model is set by **`GEMINI_MODEL`** (not hardcoded).
- So far, one synthetic smoke test with `gemini-3.5-flash-lite` passed (schema and connectivity only).
- **To do:** choose the model for real video frames (accuracy, latency, free-tier quota) and lock it in.

---

## 7. Onchain design: `FrameBountyEscrow` V3 (Arc testnet)
- **Token:** USDC ERC-20 interface `0x3600000000000000000000000000000000000000` (**6 decimals**). The constructor refuses any other token on Arc and any chain other than 5042002 (or local 31337).
- **Deployed:** `0xe613799458201e41830a5be3da5c2a7d18140da0` ([deploy tx](https://explorer.testnet.arc.io/tx/0x5fa53fe2a9d61756daada30a42dcf9d5361682f73c8a03c6a2c23f6f7cc0477b)); runtime verified. (V1 `0xd993…b063` and V2 `0xea83…dbea` remain for older jobs.)

| Function | Caller | Purpose |
|---|---|---|
| `createProtectedJob(id, reviewer, allocator, rubric, reviewSeconds, expiresAt, expectedSeconds)` | Buyer (= reviewer) | Locks the rubric, expiry (≤ 30 days) and task estimate; 1-hour payment window |
| `deposit(jobId, amount)` | Buyer | **One** fixed deposit (a retry can't double-charge) |
| `reserve(jobId, id, recipient, reward, expiresAt)` | Allocator | Commits the reward; expiry ≤ 2× the estimate and ≤ the listing expiry; recipient ≠ buyer |
| `submit(id, contentHash)` | Contributor | Locks the submitted content hash |
| `verify(id, evidenceHash)` | Allocator (oracle) | Attests a pass; sets `payAfter = now + 1h` |
| `rejectVerification(id, reasonHash)` | Allocator | Rejects before attestation; frees the reward |
| `settle(id)` | **Anyone** | Pays the fixed recipient after `payAfter` |
| `approveBatch(batchId, ids[])` | Buyer/reviewer | Early atomic payment of ≤ 20 attested clips |
| `expire(id)` | Anyone | Frees a reservation that was never submitted |
| `close(jobId)` / `refund(jobId, refundId, amount)` | Buyer | Only after expiry; only uncommitted funds |
| `rate(id, ±1)` | Paid buyer/contributor | One immutable vote per paid trade per side |

**Invariants (tested):**
- `available = deposited − committed − paid − refunded`.
- Recipients and rewards are immutable, and each clip is paid exactly once.
- No buyer veto after verification, no early refund on protected jobs, no self-trade.
- A batch reverts entirely on any bad item.

---

## 8. Safety limits (README section, a track requirement)
| Limit | Enforced by |
|---|---|
| Fixed budget, one deposit; agents hold no keys and can't move funds | Contract + architecture |
| Agents can only call allow-listed tools; anything else → 403 ("neither role can approve quality or transfer arbitrary funds") | Backend |
| Plan: ≤ 20 items, `count × reward ≤ budget`, unique requirements, 10–30 s videos; plan must match the user's stated count, type and budget | Backend (domain rules) |
| Reservation requires explicit user confirmation; reward ≤ available budget; no self-trade | Backend + contract |
| Payment only after an on-chain attestation of a passing verdict (≥ 80); uncertain → held, never paid | Policy + contract |
| Fixed recipient and reward; exact-once payment; batch ≤ 20, atomic | Contract |
| No buyer veto of verified work; contributor protected by permissionless `settle` | Contract |
| No refund before expiry; only uncommitted funds refundable | Contract |
| Allocator key ≠ buyer/reviewer; transaction destination and function selector validated; receipts matched to expected events | Backend |
| Gas limit 21k–2M and gas-price cap per transaction | Backend |
| Unpaid buyer sees only watermarked 480 px previews; originals after payment | Backend |

**Stated trust assumptions:** the allocator/oracle key and the AI are trusted (centralized). Watermarks don't stop screenshots. Ratings don't stop Sybil wallets.

---

## 9. Architecture and operations
```
Next.js 16 (one page: Buyer / Contributor workspaces; MetaMask via window.ethereum)
   │ signed-session REST
FastAPI + PostgreSQL (Alembic 0001–0007), local private media storage (.local/media)
   ├─ media worker  (python -m framebounty.worker)        ffmpeg + Gemini verification
   ├─ chain worker  (python -m framebounty.chain_worker)  allocator: reserve/verify/settle/reject/expire
   └─ Gemini REST (agents + verification)
Arc testnet ── FrameBountyEscrow V3
```
**To run the live demo, you need:**
- Postgres, the API, the media worker, the chain worker, and the web app (built with `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true`).
- Env: `APP_MODE=testnet`, `ALLOW_CHAIN_TRANSACTIONS=true`, `ALLOW_MODEL_TEXT=true`, `ALLOW_MODEL_MEDIA=true`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `ARC_RPC_URL`, `ARC_ESCROW_ADDRESS`, `ARC_ALLOCATOR_ADDRESS`, `ARC_ALLOCATOR_PRIVATE_KEY`.
- **Wallets:**
  - buyer (budget + gas)
  - contributor (gas for `submit`)
  - allocator (gas)
  
  All are funded from `faucet.circle.com` (Arc gas is paid in USDC).

---

## 10. Status and remaining work (Thu Nov 19 → Fri 10 AM)

### Verified vs pending
| Item | Status |
|---|---|
| V3 escrow deployed and runtime verified | ✅ |
| Contract, backend and browser tests, CI | ✅ local / synthetic |
| Gemini schema smoke test; buyer chat produces a plan from a real prompt | ✅ |
| **Live Arc run: fund → reserve → submit → verify → pay** | ⚠️ **Not yet done (P0)** |
| **AI accuracy on real towel clips** | ⚠️ **Not measured (P0)** |
| Phone upload over the network | ⚠️ Not tested |
| Judge-facing README on `main`, video, Devpost | ⚠️ To do |

### Work items
| Pri | Item | Owner |
|---|---|---|
| P0 | Live Arc walkthrough with two wallets; fix what breaks | Rithvik |
| P0 | Choose `GEMINI_MODEL`; film 10–20 real clips (passes, fails, large/dark variants); record accuracy and latency; tune criteria wording | Ayaan |
| P0 | **Merge to `main`**; judge-facing README (pitch, architecture, decision loop §5.3, safety limits §8, contract address, how Arc is used, test and accuracy results) | Teammate 3 (+ Rithvik for the merge) |
| P0 | Demo video (2–3 min) and Devpost answers | Teammate 4 + Teammate 3 |
| P1 | Auto-add/switch MetaMask to Arc testnet (`wallet_addEthereumChain`) | Teammate 4 |
| P1 | Fix stale copy: "complete towel fold required" (reviews.tsx:274); "Buyer releases verified rewards" (workspace.tsx:263) | Teammate 4 |
| P1 | Visible consent checkbox on upload (today consent is sent automatically) | Teammate 4 |
| P2 | Remove dead `buyer-plan.tsx`; hosted deployment if time allows | Anyone |

**Freeze 9 PM Thu · submit by 10 AM Fri · keep a recorded backup of the full flow · pre-fund all demo wallets.**

---

## 11. Demo script (5-minute final)
1. **0:00–0:40, problem:** robots learn from human demonstration video; labs need specific coverage; review and payment are manual and slow.
2. **0:40–3:40, live demo:**
   1. Buyer types the towel request → the agent asks about anything missing → plan preview → **Publish** (MetaMask: create, approve, deposit) → escrow on the Arc explorer.
   2. Contributor (second laptop or phone): "I have a large towel and a dark table" → the agent shows matching funded tasks with the buyer's reputation → reserve.
   3. Upload a pre-filmed (or live) towel fold → sign `submit` → **AI checks appear per criterion with confidence and reasons**.
   4. Show a **rejected** clip (wrong task) with its reasons.
   5. Buyer **releases early** → **USDC lands** (explorer link). Explain: "otherwise it pays automatically in one hour, and the buyer can't veto."
   6. Coverage panel shows the gap (large/dark) → **next batch auto-commissioned** for those categories.
   7. Quick **rating** of the contributor; watermarked preview vs. unlocked original.
3. **3:40–4:30, how it works:** architecture, the AI never touches money, contract limits, trust assumptions.
4. **4:30–5:00, next:** Circle email wallets, a moderator queue, annotation jobs, decentralized verification.

---

## 12. Positioning and Q&A prep
- **Why blockchain?**
  1. Escrow both sides trust: contributors know funds exist and can't be vetoed after verification.
  2. Instant USDC payouts, anywhere.
  3. Limits that the AI and the operator can't break.
  4. Public, portable reputation.
- **Why Arc?** USDC as gas means predictable fees in dollars, the native 6-decimal USDC token interface, cheap atomic batch payouts, fast finality.
- **"What if the AI is wrong?"** Only confident passes (≥ 80) are paid; confident fails are rejected with reasons; uncertain cases are held, never auto-paid. The buyer sees the per-criterion evidence. Next step: a moderator queue and calibrated thresholds from our measured accuracy.
- **"Who controls the oracle?"** Today, our allocator key (stated openly). It can't change recipients or amounts, and it can't pay unverified work. Decentralizing it is future work.
- **"Why not Stripe?"** Contributors anywhere without bank rails, a budget locked before work starts, rules the platform can't override, and exact-once on-chain settlement.

---

## 13. Submission checklist
- [ ] Code merged to **`main`** (public repo); commits are from the hackathon window (Nov 16–20) ✅
- [ ] Devpost: **Agentic Payments & AI** · **Best use of Arc** · team · answers (what, problem, how, unique, next) · tech used (Arc, USDC, Gemini, FastAPI, Next.js, Foundry)
- [ ] README: architecture, **agent decision loop**, **safety limits**, **escrow address `0xe613…0da0`**, how Arc is used, setup, test and accuracy results
- [ ] Working demo (live from a laptop) + **2–3 min video** (public link)
- [ ] Travel to Austin confirmed for Nov 21
