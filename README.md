# FrameBounty

**An AI-managed marketplace for custom data collection, with protected USDC payments on Arc.**

A buyer describes the data it needs and its budget. FrameBounty turns that request into a funded collection plan, helps contributors find suitable tasks, checks each submission against the agreed rubric, and pays verified work from escrow. After each confirmed payout, the system publishes a small next batch aimed at the categories that are still missing.

This integrated branch includes in-app video capture, Circle Google login (email
OTP optional), optional browser wallets, and guarded Arc mainnet support. Live
Circle login and real-USDC settlement still need account setup and validation;
no real funds have been spent. See [Circle setup](docs/CIRCLE_SETUP.md).
Vercel/Railway/Supabase deployment configuration and private object storage are
prepared, with no hosted deployment performed: [hosting guide](docs/DEPLOY.md).

Robotics demonstration video is the launch example, not the product boundary: “20 towel-folding videos, including at least five large towels and five dark surfaces, under a 20 USDC contributor budget.”

> **UBC 2026 Hackathon**
> Main track: **Agentic Payments & AI**
> Chain award: **Best use of Arc**
> Demo video: **TODO before submission**
> Arc testnet escrow V3: [`0xe613799458201e41830a5be3da5c2a7d18140da0`](https://explorer.testnet.arc.io/address/0xe613799458201e41830a5be3da5c2a7d18140da0)

## Why this exists

Labs need specific coverage, not a folder of interchangeable clips. A robotics team may need an action filmed with particular objects, surfaces, viewpoints, or end states. Today that work often depends on contractors, spreadsheets, manual review, and manual payment.

FrameBounty addresses four problems:

- **Planning:** turn an open-ended request into fixed requirements, quantities, rights, and rewards.
- **Discovery:** match contributors to real funded tasks they can complete with the equipment and time they have.
- **Verification:** assess every required criterion and hold uncertain work rather than treating uncertainty as success.
- **Coverage:** spend the remaining budget on missing categories instead of repeatedly buying the easiest example.

## Product flow

### Buyer

1. Sign in with MetaMask on Arc testnet by signing a server challenge. The login signature grants no payment authority.
2. Describe an image or video collection in chat. The buyer agent asks for a missing count, budget, or media type instead of guessing.
3. Review the plan, including the fixed budget, per-item reward, requirements, usage rights, task estimate, and expiry.
4. Publish through one guided wallet flow: `createProtectedJob`, exact USDC `approve`, then `deposit`.
5. Review AI findings and coverage. The buyer may pay verified work early with one atomic batch transaction; otherwise protected work becomes permissionlessly settleable after the one-hour payment window.
6. Export paid data and a manifest, rate contributors, and refund uncommitted funds after the collection expires.

### Contributor

1. Sign in with a wallet different from the buyer wallet.
2. Tell the contributor agent what equipment, objects, and time are available.
3. Review ranked, currently funded listings. Confirm the exact task, version, reward, deadline, and rights before reservation.
4. Upload the required JPEG/PNG image, or open the in-app camera after reservation
   and record/review a 10–30 second video. Video file selection is unavailable.
   Recording uses MP4 when supported and WebM otherwise; camera access begins
   only after **Open camera**, without requesting audio. Authorize `submit(contentHash)`
   with the signed-in wallet. A browser capture token does not prove authenticity.
5. See per-criterion AI findings, retry or rejection reasons, the payment window, and the confirmed payment state.
6. Rate the buyer after a confirmed paid trade.

Self-trading is blocked. Fixture listings and fixture rewards are visibly simulated and never represent blockchain funds.

## Architecture

```text
Next.js 16 / React 19
  Buyer and contributor workspaces
  MetaMask through window.ethereum
              |
              | signed-session REST
              v
FastAPI / PostgreSQL
  Buyer agent and contributor agent
  Plan, search, reservation, coverage, export, and authorization services
  Private local media adapter and watermarked previews
  Durable transaction intents and receipt reconciliation
        |                         |
        | media jobs              | chain intents
        v                         v
FFmpeg + Gemini             Arc chain worker
  bounded decode              reserve / verify / reject
  five sampled frames         settle / expire
  criterion JSON              receipt projection
        |                         |
        +------------+------------+
                     v
             FrameBountyEscrow V3
                  Arc testnet
```

| Layer | Implementation |
| --- | --- |
| Web | Next.js 16, React 19, TypeScript, MetaMask EIP-1193 provider |
| API | FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL |
| AI | Google Gemini REST `generateContent` with a server-defined JSON schema; model selected by `GEMINI_MODEL` |
| Media | FFmpeg/ffprobe, Pillow, SHA-256, perceptual hashes |
| Private storage | Local development disk or Supabase objects with a private decoder cache |
| Contract | Solidity 0.8.24, OpenZeppelin, Foundry-compatible Arc toolchain |
| Chain | Arc testnet, native USDC gas, canonical USDC ERC-20 interface |

## Agent decision loop

The language models interpret requests and observations. Deterministic application code and the escrow contract enforce quantities, authorization, state transitions, and money movement.

```text
PLAN
  Buyer agent drafts a plan from chat.
  Server validation requires the stated count, media type, budget, requirements, and rights.
  Missing facts cause a question, not an invented value.

FUND
  Buyer signs createProtectedJob, exact USDC approval, and one fixed deposit.
  Drafts remain private until the funding receipt is verified.

PUBLISH
  The initial batch exposes at most two funded task slots.

MATCH
  Contributor agent searches actual open funded listings and ranks them using the contributor's stated resources.
  The contributor confirms the exact task, version, reward, rights, and deadline.
  The allocator records reserve() on chain after rechecking availability.

SUBMIT
  Contributor uploads private media and signs submit(sha256).
  The reservation deadline is bounded by the collection expiry and twice the task estimate.

VERIFY
  The media worker validates and decodes the file.
  Video sampling uses five timestamps: start, quarter, midpoint, three quarters, and end minus 250 ms.
  Gemini returns pass, fail, or uncertain for task completion, visibility, and every task criterion, with an integer confidence, explanation, and supplied timestamps.

DECIDE
  Deterministic threshold: 80.
  Every mandatory criterion passes at 80 or above: verified.
  Any mandatory criterion fails at 80 or above: rejected with reasons.
  Anything else, including provider failure: pending and non-paying. Protected work retries after a cooldown.

ATTEST AND SETTLE
  The allocator calls verify(id, evidenceHash), which starts the one-hour payment window.
  The buyer may pay earlier with approveBatch for up to 20 verified submissions.
  After the window, anyone may call settle(id); the app keeper normally does so.
  Recipients and rewards were fixed at reservation and each obligation can pay once.

REPLAN
  After a confirmed payout, code recomputes requirement deficits from accepted work, active obligations, and open slots.
  It publishes at most two new slots for the missing categories without exceeding the funded budget.

STOP
  Coverage is complete, the remaining budget cannot fund another slot, or the collection expires.
  After expiry, the buyer may refund only uncommitted funds.
```

## Verification policy

The verifier evaluates the post that the buyer actually approved; it does not contain towel-specific business logic.

- Videos must be MP4/MOV, 10–30 seconds, and at most 100 MiB. Images must be JPEG/PNG, at most 20 MiB and 16 megapixels.
- The worker fully probes and decodes media before model assessment.
- Five video frames are scaled to fit within 640 px. Still images are re-encoded as metadata-free JPEG samples.
- Mandatory checks are `task_completion`, `visibility`, and the reserved task’s target criteria.
- Visibility requires the relevant hands and task objects for a human-performed action. A sharp but out-of-frame attempt cannot pass.
- Completion requires evidence that the requested action happened and that its end state is visible. Merely holding the objects or attempting the action is insufficient.
- Exact hashes and perceptual hashes flag potential duplicates. Similarity alone does not reject a submission.
- Confidence is reported by the model and is not a calibrated probability.
- The system does not claim that sampled frames prove consent, ownership, genuine capture, physical dimensions, or scientific ground truth.

Uncertain and unavailable-provider outcomes remain pending and cannot authorize payment.

## Safety limits and trust assumptions

| Limit | Enforcement |
| --- | --- |
| Buyer tools are limited to `draft_plan`, `inspect_job`, and `next_batch`. Contributor tools are limited to `search_tasks`, `read_task`, `prepare_confirmation`, `reserve_task`, and `my_work`. | Backend authorization and tool schemas |
| Agents hold no wallet keys and cannot send arbitrary transactions. | Architecture and backend |
| Plans contain no more than 20 items and cannot spend more than the approved integer-atomic budget. | Backend domain validation |
| Reservation requires explicit task-specific confirmation and a fresh atomic availability check. | Backend and contract |
| One fixed deposit funds a protected job. A retry cannot double-deposit. | Contract and receipt matching |
| Each reservation has an immutable recipient and reward and can pay exactly once. | Contract |
| The buyer cannot veto protected work after oracle verification. | Contract |
| `settle` is permissionless after the one-hour window. | Contract |
| Early release batches contain at most 20 items and revert atomically if any item is invalid. | Contract |
| The buyer cannot refund before expiry and can refund only uncommitted funds. | Contract |
| Buyer and contributor must be different wallets. | Backend and contract |
| Transaction destination, function selector, chain, receipt, and expected event are validated before database projection. | Backend chain services |
| The buyer sees reduced, watermarked previews before payment. Originals unlock only after confirmed payment. | Backend media authorization |

Trust remains explicit:

- The allocator/oracle key and Gemini judgment are centralized. A compromised or incorrect oracle could attest a bad result. The contract still prevents it from changing the reserved recipient or reward.
- Private media storage and authentication are service-operated.
- Watermarks discourage reuse but cannot prevent screenshots, cropping, or model-based removal.
- Paid-trade ratings do not prevent collusion, retaliation, or Sybil wallets.
- Worker downtime can delay transactions. Permissionless settlement remains available on chain after the payment window.

## How FrameBounty uses Arc

Arc testnet is the enforceable payment and reputation layer, not a decorative deployment target.

- Chain ID: `5042002` (`0x4cef52`)
- RPC: `https://rpc.testnet.arc.io`
- Explorer: `https://explorer.testnet.arc.io`
- Faucet: [`https://faucet.circle.com`](https://faucet.circle.com)
- Escrow token interface: `0x3600000000000000000000000000000000000000`
- Current escrow V3: [`0xe613799458201e41830a5be3da5c2a7d18140da0`](https://explorer.testnet.arc.io/address/0xe613799458201e41830a5be3da5c2a7d18140da0)
- Verified deployment transaction: [`0x5fa53f…477b`](https://explorer.testnet.arc.io/tx/0x5fa53fe2a9d61756daada30a42dcf9d5361682f73c8a03c6a2c23f6f7cc0477b)

Arc uses USDC as its native gas asset. The escrow uses the canonical USDC ERC-20 interface with 6-decimal token amounts, while native gas accounting uses 18 decimals. FrameBounty keeps those unit boundaries separate.

The contract provides:

- a fixed collection budget, rubric hash, task estimate, and expiry;
- immutable per-task recipients and rewards;
- oracle verification evidence and a one-hour payment window;
- permissionless exact-once settlement;
- an optional atomic early-release batch;
- refunds of uncommitted funds after expiry;
- one permanent `+1` or `-1` vote per side after a paid trade.

V1 and V2 deployments remain bound to their original funded jobs. Application migrations do not move old escrow funds or assign new V3 guarantees to old bytecode.

**Current evidence:** V3 is deployed and its runtime was verified on Arc testnet. A complete funded V3 buyer-to-contributor walkthrough has not yet been run, so deployment is not presented as payout evidence.

**TODO before submission:** add public links for a real collection’s creation, deposit, reservation, submission, verification, and payout transactions after the team completes the funded testnet walkthrough.

## Validation results

| Gate | Result | What it proves |
| --- | --- | --- |
| Backend tests with PostgreSQL | **210 passed, 24 skipped** | Domain, auth, private storage, hosted config, media, agents, verification, protected marketplace, and HTTP behavior. Chain cases run separately. |
| Solidity contract tests | **29 passed** | Security, accounting, protected settlement, ratings, mainnet constructor guards and local fuzz tests. |
| PostgreSQL plus local-chain integration | **25 passed** | Receipt-gated funding, reservations, submission, verification, payout/recovery, and protected flows against local contracts. |
| Web unit tests | **15 passed** | API error semantics, Arc switching, Circle intent dispatch, camera behavior and durable publishing. |
| Web typecheck and production build | **passed** | The committed Next.js application compiles and builds. |
| Browser end-to-end | **8 passed, 1 skipped** | Isolated Chromium flow with wallet signatures, PostgreSQL, API, Next.js, FFmpeg, and fixture model/chain boundaries. |
| Fixture launcher lifecycle | **passed** | Migrations, API, media worker, and web started; API and web returned HTTP 200; recorded processes stopped cleanly. |
| Real labeled-clip sanity check | **3 of 3 decisions correct, 0 false pay** | A small earlier run using `gemini-3.5-flash-lite`; this is not a statistically meaningful accuracy benchmark. |
| Arc V3 deployment | **runtime verified** | Correct bytecode exists at the listed Arc testnet address. It does not prove a funded collection or payout. |
| Funded live Arc flow | **pending** | No claim yet for buyer funding through contributor payout on Arc testnet. |

The three-clip model sanity check used two successful physical tasks and one failed task. The verification wording was later tightened to require visible hands/task objects and a visible end state. A live recheck of those private clips remains pending explicit permission to send reduced sampled frames to Google Gemini. Local prompt, adapter, and deterministic policy tests pass, but they do not replace that live recheck.

## Run locally

### Prerequisites

- Python 3.12 or newer
- Node.js 22
- PostgreSQL, through Docker Compose or another reachable server
- MetaMask or another compatible injected wallet
- Testnet by default; real-USDC mainnet remains explicitly gated and not activated

### Install

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e './services/api[test]'
.\.venv\Scripts\python.exe scripts/setup_media_tools.py
npm ci --prefix apps/web
Copy-Item .env.example .env
docker compose up -d postgres
```

The API does not automatically load `.env`. The demo launcher loads it without displaying values, applies migrations, and starts the required child processes. Never place a Gemini key or signing key in a `NEXT_PUBLIC_` setting.

### Fixture walkthrough

Fixture mode makes no Arc transaction and sends no media to Gemini. It clears live credentials from its child processes and labels every simulated result.

```powershell
.\scripts\demo.ps1 -Mode fixture -Action start
.\scripts\demo.ps1 -Action status
# Open http://localhost:3000
.\scripts\demo.ps1 -Action stop
```

See [`docs/DEMO.md`](docs/DEMO.md) for the complete runbook, phone/LAN setup, evidence checklist, and troubleshooting.

### Arc testnet mode

Use three distinct, test-only wallets:

1. Buyer wallet with the collection budget and gas.
2. Contributor wallet with gas for `submit(contentHash)`.
3. Dedicated allocator/oracle wallet with gas for reservation, verification, rejection, expiry, and settlement transactions.

Required `.env` settings:

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
APP_MODE=testnet
AUTH_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000

GEMINI_API_KEY=<server-side-secret>
GEMINI_MODEL=gemini-3.5-flash-lite
ALLOW_MODEL_TEXT=true
ALLOW_MODEL_MEDIA=true

ARC_RPC_URL=https://rpc.testnet.arc.io
ARC_CHAIN_ID=5042002
ARC_ESCROW_ADDRESS=0xe613799458201e41830a5be3da5c2a7d18140da0
ARC_ALLOCATOR_ADDRESS=<dedicated-public-address>
ARC_ALLOCATOR_PRIVATE_KEY=<dedicated-local-secret>
ALLOW_CHAIN_TRANSACTIONS=true
NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true
```

Then run:

```powershell
.\scripts\demo.ps1 -Mode testnet -Action start
```

For a production web build, load the same public configuration before `npm run build`; see `docs/DEMO.md` for the exact command.

### Checks

```powershell
# Backend and real PostgreSQL integration tests
$env:TEST_DATABASE_URL=$env:DATABASE_URL
.\.venv\Scripts\python.exe -m pytest services/api/tests -q

# Contract and local-chain gates
.\scripts\test-contract.ps1
.\.venv\Scripts\python.exe scripts/test_chain.py

# Browser end-to-end
.\.venv\Scripts\python.exe scripts/test_e2e.py

# Web unit, types, and production build
npm --prefix apps/web run test:publishing
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Ordinary automated tests do not call Gemini or transfer Arc testnet funds.

## Repository map

```text
apps/web/       Next.js buyer and contributor workspaces
services/api/   FastAPI services, workers, migrations, and tests
contracts/      FrameBountyEscrow Solidity source and Foundry tests
docs/           Architecture, decisions, test matrix, live evidence, and demo runbook
scripts/        Setup, deployment, inspection, evaluation, and test harnesses
```

## Current limitations

- The complete funded Arc flow has not been validated through the browser.
- AI verification and the allocator/oracle key remain centralized.
- Phone/LAN upload has not been proven on a physical phone.
- Automatic hashless recovery, fee replacement, and cancellation of unsigned pending allocations remain incomplete.
- Provider failure can keep protected funds committed until the service and verification process resume.
- Hosting configuration is prepared; live provider connectivity and Docker image
  build remain unverified (the local Docker daemon is unavailable).

## Next steps

- Complete and record the funded Arc walkthrough with three pre-funded wallets.
- Add a moderation path for uncertain work and measure model behavior on a larger, consented dataset.
- Finish Circle account setup and validate Google/email sign-in; gas sponsorship
  remains separate from the implemented user-controlled EOA integration.
- Extend the marketplace to annotation and labeling jobs.
- Replace the single trusted oracle with a more decentralized verification design.

## Team

- **Rithvik Reddy Siddenki** — repository owner and full-stack implementation
- **Ayaan Ameen** — AI verification evaluation and integration
- **TODO before submission:** add the other two team members, roles, and links

Built during the UBC 2026 hackathon window.
