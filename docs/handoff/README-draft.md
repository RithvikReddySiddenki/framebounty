# FrameBounty

**An AI-managed marketplace for custom training data, with escrow and payment in USDC on Arc.**

A lab tells FrameBounty's buyer agent what data it needs and its budget. The budget is locked in an escrow contract on Arc, contributor agents help people find tasks they can do at home, AI checks every submission against the agreed rubric, and **verified work is paid automatically**. The system then commissions the examples that are still missing.

Robotics demonstration video is our launch use case: *"20 videos of people folding towels, at least 5 with large towels and 5 on dark surfaces, under 20 USDC."*

> **UBC 2026 Hackathon** · Track: **Agentic Payments & AI** · Chain award: **Best use of Arc**
> 🎥 Demo video: `<ADD LINK>` · 📜 Escrow (Arc testnet): [`0xe613799458201e41830a5be3da5c2a7d18140da0`](https://explorer.testnet.arc.io/address/0xe613799458201e41830a5be3da5c2a7d18140da0)

---

## The problem
Robot foundation models learn from human demonstrations, and labs need **specific** coverage (object sizes, surfaces, conditions), not just "more video". Today that means contractors, spreadsheets and manual review:
- **Review doesn't scale.** Someone has to watch every clip.
- **Coverage drifts.** Contributors film the easiest variant, and the budget runs out before the gaps are filled.
- **Trust runs both ways.** Contributors fear doing work and not getting paid. Buyers fear paying for bad data.

## What FrameBounty does
1. **Buyer** describes the dataset in chat. The **buyer agent** asks about anything missing and drafts a plan (count, requirements, reward per item, deadline).
2. Buyer **publishes with one MetaMask flow**: the escrow job is created, the exact USDC budget is approved and deposited on Arc. The budget, rubric and deadline are now locked.
3. **Contributor** tells their **contributor agent** what they have ("a large towel, a dark table, 20 minutes"). The agent searches **real funded listings**, ranks them, and reserves one after the contributor confirms.
4. Contributor uploads a 10–30 s clip and signs its content hash on chain.
5. **AI verification** samples frames and scores every requirement (pass, fail or uncertain, with a confidence, an explanation and frame timestamps).
6. **Confident passes are attested on chain and paid automatically** after a 1-hour window. The buyer can release earlier, but **can't veto verified work**. Confident failures are rejected with reasons. Uncertain results are **held, never paid automatically**.
7. After each payout, FrameBounty **checks coverage and commissions the missing categories** (e.g. more large towels on dark surfaces) from the remaining budget.

Extras:
- Watermarked previews until payment, with originals unlocked once paid.
- **On-chain buyer and contributor ratings.**
- Refund of unused budget after the deadline.
- ZIP + manifest export of accepted data.

---

## Architecture
```
┌───────────────────────────── Next.js 16 web app ─────────────────────────────┐
│  Buyer workspace (chat → plan → publish/fund, review, release, export, rate)  │
│  Contributor workspace (chat → find work → reserve, upload, submit, rate)     │
│  Wallet: MetaMask (EIP-1193) on Arc testnet                                   │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ signed-session REST
┌───────────────────────────────▼───────────────────────────────────────────────┐
│ FastAPI + PostgreSQL                                                           │
│  • Buyer & contributor agents (Gemini, role-scoped tools, no keys)             │
│  • Media worker: ffprobe/ffmpeg → frames → Gemini rubric verdict → policy      │
│  • Chain worker (allocator/oracle key): reserve · verify · settle · reject     │
│  • Durable transaction intents, receipt verification, crash recovery           │
│  • Private media storage, watermarked previews, coverage & replanning          │
└───────────────────────────────┬───────────────────────────────────────────────┘
                                │ JSON-RPC
                  ┌─────────────▼─────────────┐
                  │ Arc testnet (chain 5042002)│
                  │ FrameBountyEscrow V3 + USDC│
                  └────────────────────────────┘
```

| Layer | Tech |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript, MetaMask (`window.ethereum`) |
| Backend | FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL |
| AI | Google Gemini (`generateContent` with JSON schema), model set via `GEMINI_MODEL` |
| Media | FFmpeg/ffprobe, Pillow, ImageHash |
| Contracts | Solidity 0.8.24, OpenZeppelin, Arc Foundry |
| Chain | Arc testnet, USDC ERC-20 interface `0x3600…0000` (6 decimals) |

---

## Agent decision loop
The agents plan and search. **Money only moves through user wallet signatures or deterministic rules enforced by the contract.**

```
PLAN      Buyer agent turns chat into a plan; it must match the user's stated count, media type and budget.
          Missing facts → the agent asks instead of guessing.
FUND      Buyer signs createProtectedJob → approve → deposit (one fixed budget, rubric hash, expiry).
PUBLISH   First batch: 2 task slots.
MATCH     Contributor agent extracts what the contributor has → searches real funded listings → ranks.
          Contributor confirms → allocator records reserve() on chain (deadline ≤ 2× task estimate).
SUBMIT    Contributor uploads → signs submit(sha256) → verification job queued.
VERIFY    Worker decodes media, samples 5 frames (640px), asks Gemini to score each rubric criterion:
          {result: pass|fail|uncertain, confidence 0–100, explanation, timestamps}.
DECIDE    Deterministic policy (threshold 80):
            all mandatory criteria pass ≥80  → VERIFIED
            any mandatory criterion fails ≥80 → REJECTED (reasons shown to contributor)
            otherwise / provider error       → RETRY (×3, then every 5 min); funds stay held, never auto-paid
ATTEST    Allocator calls verify(id, evidenceHash) → payment unlocks 1 hour later
          or rejectVerification(id, reasonHash) → reward returns to the budget.
SETTLE    After the window, anyone may call settle(id) (our keeper does) → USDC to the contributor.
          The buyer may pay earlier with approveBatch (≤20 clips, atomic).
REPLAN    After each confirmed payout: per-category deficit = target − (accepted + pending + open slots)
          → publish ≤2 new slots tagged with the missing categories, within the remaining budget.
STOP      Coverage met · budget exhausted · listing expired → buyer refunds unused funds.
```

## Safety limits
| Limit | Enforced by |
|---|---|
| Agents hold **no keys** and can only call allow-listed tools: buyer `draft_plan / inspect_job / next_batch`; contributor `search_tasks / read_task / prepare_confirmation / reserve_task / my_work`. Anything else → 403. | Backend |
| **Neither agent can approve quality or transfer funds.** Reserving requires explicit user confirmation. | Backend |
| Plan rules: ≤ 20 items, `count × reward ≤ budget`, unique requirements, 10–30 s videos | Backend |
| **One fixed deposit** per job (retries can't double-charge) | Contract |
| Payment only after an **on-chain attestation** of a passing verdict; uncertain → held | Policy + contract |
| **Immutable recipient and reward**, exact-once payment, atomic batches ≤ 20 | Contract |
| **No buyer veto** after verification; **permissionless `settle`** protects contributors if our service is down | Contract |
| No refund before the deadline; only uncommitted funds are refundable | Contract |
| No self-trade (buyer ≠ contributor); reservation expiry ≤ 2× task estimate | Contract |
| Allocator key is dedicated (never the buyer/reviewer); each transaction's destination and function selector are validated; receipts matched to expected events | Backend |
| Unpaid buyers see only watermarked 480 px previews; originals unlock after payment | Backend |

**Trust assumptions (stated openly):**
- The allocator/oracle key and the AI judgment are centralized. The oracle **can't** change recipients or amounts, or pay unverified work.
- Model confidence is model-reported, not calibrated.
- Watermarks discourage, but can't prevent, screenshots.
- Ratings require a paid trade but don't stop Sybil wallets.

---

## How we use Arc
- **USDC is the gas token,** so buyers and contributors see fees in dollars. Every amount in the app is USDC.
- The escrow uses Arc's **USDC ERC-20 interface** (`0x3600000000000000000000000000000000000000`, 6 decimals). It never mixes in native 18-decimal amounts, and the constructor refuses any other token or chain.
- **Escrow V3** ([`0xe613…0da0`](https://explorer.testnet.arc.io/address/0xe613799458201e41830a5be3da5c2a7d18140da0), [deploy tx](https://explorer.testnet.arc.io/tx/0x5fa53fe2a9d61756daada30a42dcf9d5361682f73c8a03c6a2c23f6f7cc0477b)) provides:
  - a fixed budget per job with a locked rubric and deadline
  - per-task reservations with immutable rewards
  - oracle attestation, then a 1-hour window, then **permissionless settlement**
  - **atomic batch payouts** (one signature pays up to 20 contributors)
  - refunds of uncommitted funds after the deadline
  - **on-chain counterparty ratings**
- Built and tested with **Arc Foundry**.
- **Live testnet evidence:** `<ADD: funding tx, reservation tx, verify tx, payout tx links from the live run>`

## Results
| What | Result |
|---|---|
| Contract tests (Foundry, incl. fuzz) | 27 passing |
| Backend tests (pytest, real PostgreSQL) | `<N>` passing |
| Browser end-to-end (Playwright) | 9 passing |
| Live Arc walkthrough (fund → reserve → submit → verify → pay) | `<ADD: done + tx links>` |
| **AI verification on real towel clips** | `<ADD: e.g. "N clips: X correct passes, Y correct rejections, Z uncertain; median latency T s; model GEMINI_MODEL">` |

---

## Run it locally
**Prerequisites:** Python 3.12, Node 22, Docker (for Postgres), FFmpeg, MetaMask with **Arc testnet** added (chain ID `5042002`, RPC `https://rpc.testnet.arc.io`, currency USDC, explorer `https://explorer.testnet.arc.io`). Get testnet USDC from [faucet.circle.com](https://faucet.circle.com).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e './services/api[test]'
.\.venv\Scripts\python.exe scripts/setup_media_tools.py
Copy-Item .env.example .env        # then fill in values (see below)
docker compose up -d postgres
./scripts/load-env.ps1
.\.venv\Scripts\python.exe -m alembic -c services/api/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn framebounty.main:app        # API
.\.venv\Scripts\python.exe -m framebounty.worker                  # media/AI worker (new terminal)
.\.venv\Scripts\python.exe -m framebounty.chain_worker            # chain worker (new terminal)
cd apps/web; npm ci; npm run dev                                  # web (new terminal)
```
Open http://localhost:3000 and sign in with MetaMask.

**Live testnet configuration (`.env`):**
```
APP_MODE=testnet
ALLOW_CHAIN_TRANSACTIONS=true
NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true
ALLOW_MODEL_TEXT=true
ALLOW_MODEL_MEDIA=true
GEMINI_API_KEY=...            # server-side only
GEMINI_MODEL=...              # e.g. the model used in Results
ARC_RPC_URL=https://rpc.testnet.arc.io
ARC_ESCROW_ADDRESS=0xe613799458201e41830a5be3da5c2a7d18140da0
ARC_ALLOCATOR_ADDRESS=...     # dedicated allocator, funded with testnet USDC for gas
ARC_ALLOCATOR_PRIVATE_KEY=... # never a buyer/contributor key
```
Use **two different wallets** for buyer and contributor (self-trade is blocked). Both need testnet USDC for gas. **Fixture mode** (`APP_MODE=fixture`) runs a clearly labeled simulated demo with no chain or model calls.

**Checks:**
```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q
.\scripts\test-contract.ps1
.\.venv\Scripts\python.exe scripts/test_chain.py   # local chain + PostgreSQL
.\.venv\Scripts\python.exe scripts/test_e2e.py     # Chromium end-to-end
```

## Repository map
```
apps/web/            Next.js app (workspace, post composer, funding, reviews, upload, ratings)
services/api/        FastAPI app, agents, verification worker, chain worker, migrations, tests
contracts/           FrameBountyEscrow.sol + Foundry tests
docs/                architecture, state machine, decisions (0001–0012), test matrix, live evidence
scripts/             setup, deploy, inspect, smoke and test harnesses
```

## What's next
- **Circle email-login wallets** and gas sponsorship, so contributors never install a wallet.
- A **moderator queue** for uncertain clips, plus thresholds calibrated from measured accuracy.
- **Annotation and labeling jobs** using the same escrow and verification flow.
- Decentralized or multi-party verification instead of a single oracle key.
- Hosted deployment and native mobile capture.

## Team
`<Names · roles · links>`

*Built during UBC 2026 (Nov 12–20). Code and IP retained by the team.*
