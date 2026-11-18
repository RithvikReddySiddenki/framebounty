# framebounty
An AI-powered marketplace where labs and developers commission custom data, agents manage tasks and budgets, and contributors find paid work. Built on Arc with USDC payments, featuring a robotics data collection demo.

## Current status

Implemented locally: signed EOA wallet login, buyer-owned versioned draft plans,
database-backed filtered task search, explicit version/reward confirmation,
atomic and idempotent fixture reservations, private reservation lists, strict
money/coverage rules, private phone uploads, durable verification jobs, real
FFmpeg decoding and sampled frames, human review, next-batch allocation, and
accepted-data manifest/streaming ZIP export. The Solidity escrow passes local-EVM
security/fuzz tests. Fixtures are clearly labeled and never represent real funds.
Role-scoped buyer/contributor conversations and durable tool decisions are implemented.
Durable chain intents, exact receipt verification and wallet-owned fixed-budget
funding/publication and receipt-gated reservation/submission/review accounting are
implemented and tested against a local chain. The canonical escrow is now deployed
and runtime-verified on Arc testnet; a synthetic Gemini smoke passed. The complete
funded browser/physical-task workflow and model evaluation remain pending. See
[live validation evidence](docs/live-validation.md); deployment is not job funding.
See [workboard](docs/workboard.md).

In the buyer conversation, request the towel example and review its proposal in
the editor before confirming the plan. The fixture planner is a fixed example,
not a general prompt interpreter. In the contributor workspace, edit equipment/time,
then send a message to search actual listings. Review and explicitly confirm the
agent's specific task before uploading. In an owned collection's buyer conversation,
`Inspect my coverage` observes records; `Commission next batch` publishes within the
approved simulated policy. Saved conversations and pending intentions can be resumed.
Neither agent can approve quality. Live Gemini text additionally requires
`ALLOW_MODEL_TEXT=true` and an account-verified model/key configured locally.

## Local setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e './services/api[test]'
.\.venv\Scripts\python.exe scripts/setup_media_tools.py
Copy-Item .env.example .env
docker compose up -d postgres
$env:DATABASE_URL='postgresql+psycopg://framebounty:framebounty@localhost:5432/framebounty'
$env:APP_MODE='fixture'
.\.venv\Scripts\python.exe -m alembic -c services/api/alembic.ini upgrade head
.\.venv\Scripts\python.exe -m uvicorn framebounty.main:app --reload
# In another terminal:
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000 and API docs at http://localhost:8000/docs.
The API does not automatically load `.env`. Run `./scripts/load-env.ps1` in each
terminal before starting the API or workers; it loads documented settings without
displaying values or evaluating shell expressions. The explicit shell exports
above are an alternative for fixture mode. Do not put any
Gemini or signing secret in a `NEXT_PUBLIC_` variable. No Gemini key is needed for
draft editing or deterministic search. Saving or reserving requires a browser
wallet on Arc testnet and a signed login challenge (no payment authority).

To seed clearly labeled **simulated** listings, explicitly set `APP_MODE=fixture`
and run:

```powershell
.\.venv\Scripts\python.exe -m framebounty.demo --buyer 0xYOUR_PUBLIC_DEMO_WALLET
```

Use the contributor workspace to filter equipment (e.g. `phone,towel,dark_table`),
review the displayed task terms, and confirm a reservation. Seed rewards are not
redeemable. Re-running seed creates another
fixture job; it never resets or deletes other users' data.

Alternatively, save a plan in the buyer UI, explicitly confirm simulated funding,
and publish the first two fixture slots. The contributor can reserve, acknowledge
the displayed usage rights, and upload a 10–30 second MP4/MOV. In another terminal,
set the same `DATABASE_URL` and `APP_MODE=fixture` and run:

```powershell
.\.venv\Scripts\python.exe -m framebounty.worker
```

The reviewer loads their collections, watches the full video and timestamped frames,
confirms task completion and category definitions, and accepts/rejects with a reason.
Acceptance updates the **simulated** ledger and overlapping coverage. It does not
show a confirmed payment. Commission another fixture batch or export accepted media.
For phone/LAN testing configure `AUTH_ORIGIN` and `NEXT_PUBLIC_API_URL` for that origin
and use secure hosting for wallet/browser capabilities; actual phone testing is pending.

The optional `docker compose --profile worker up -d worker` imposes a 768 MiB
memory limit and one CPU. Apply migrations first and configure `LOCAL_UID`/`LOCAL_GID`
to match ownership of `.local/media` on Linux. Container image/runtime is not yet tested.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q
# Enable real PostgreSQL integration tests (isolated schemas, not SQLite):
$env:TEST_DATABASE_URL=$env:DATABASE_URL
.\.venv\Scripts\python.exe -m pytest services/api/tests -q
cd apps/web
npm run typecheck
npm run build
```

`scripts/check.ps1` runs unit/HTTP tests (plus PostgreSQL tests when
`TEST_DATABASE_URL` is set), typecheck and production build. If Windows profile
temp permissions fail, add `--basetemp=.local/pytest-UNIQUE_RUN_NAME` using a fresh
workspace directory. Additional gates from the repository root:

```powershell
npm ci --prefix contracts
.\.venv\Scripts\python.exe scripts/setup_arc_tools.py
.\scripts\test-contract.ps1
.\.venv\Scripts\python.exe scripts/export_contract.py --check
# Owned ephemeral local chain + real PostgreSQL transaction/funding tests:
.\.venv\Scripts\python.exe scripts/test_chain.py
# Isolated Chromium + real PostgreSQL/FFmpeg workflow:
$env:PLAYWRIGHT_BROWSERS_PATH="$PWD/.local/browsers"
npm exec --prefix apps/web -- playwright install chromium
.\.venv\Scripts\python.exe scripts/test_e2e.py
# Explicit read-only live Arc preflight; does not send transactions:
.\.venv\Scripts\python.exe scripts/inspect_arc.py
```

The browser harness uses dedicated ports 3002/8002, a random temporary PostgreSQL
schema and generated non-human video. It removes its schema and stops its servers.
No live provider calls or testnet fund transfers occur in ordinary tests.
See [test matrix](docs/test-matrix.md), [architecture](docs/architecture.md)
and [state machine](docs/state-machine.md).

Optional Arc funding requires a separately deployed canonical escrow,
`APP_MODE=testnet`, `ALLOW_CHAIN_TRANSACTIONS=true`, and public
`ARC_RPC_URL`, `ARC_ESCROW_ADDRESS`, `ARC_ALLOCATOR_ADDRESS` configuration.
Use a dedicated allocator address. Set `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true`
when building the web app to expose saved-job funding/recovery controls. Buyer
wallets sign creation, exact-budget allowance and deposit separately; no buyer key
is configured on the server. Apply Alembic through migration 0005 first. Keep live
validation disabled until the canonical escrow and funded testnet wallets are ready.
The actual Arc wallet flow has not yet been validated.

Funding confirmations are tied to the saved plan hash. Wallet-response recovery
accepts its existing hash from wallet activity; automatic event discovery and
fee replacement are pending. Verified reverted/invalid intentions are terminal;
the current UI does not automatically create another signing attempt. Server-side
retry tests reuse persisted signed bytes and nonce, including after lost responses.

For testnet reservation dispatch, configure only the dedicated allocator's
`ARC_ALLOCATOR_PRIVATE_KEY` locally. Never use a buyer/reviewer key. Run the durable
chain worker alongside the media worker:

```powershell
.\.venv\Scripts\python.exe -m framebounty.chain_worker
```

The contributor confirms a task, waits for `reserved`, uploads and confirms its
content hash in their wallet. Human review records the decision before a separate
reviewer-wallet transaction. Only its verified receipt changes payment/coverage.
Expiry/timeout controls also wait for chain receipts. `projected` recovers a crash
between receipt verification and ledger update. Testnet accepted data is included
in exports/replanning; fixture data remains explicitly simulated. Pending unsigned
allocations have no automatic cancellation, and close/refund UI is still pending.

For a new local allocator, `python scripts/setup_local_allocator.py` creates a
dedicated wallet directly in ignored `.env` and prints only its public address.
It preserves existing allocator settings and leaves live transactions disabled.
Fund that public address using the Arc testnet faucet; keep buyer/reviewer wallets
separate. Put the Gemini API key only in `GEMINI_API_KEY` in `.env`; account/model
access must be checked before selecting `GEMINI_MODEL` or enabling inference.

`python scripts/deploy_arc.py` prepares one bounded canonical deployment and saves
its signature privately in `.local/arc-deployment.json`; it does not broadcast.
After explicit deployment authorization, `--broadcast` reuses that same signature
and verifies receipt/runtime before saving the escrow address in `.env`. It never
enables application flags. Parallel deployment processes are excluded by an OS lock.

Model metadata access does not establish free-tier billing or inference quality.
`scripts/smoke_gemini.py` requires explicit `ALLOW_LIVE_MODEL_SMOKE=true` and human
confirmation `GEMINI_FREE_TIER_CONFIRMED=true` that billing is disabled. It sends
only generated synthetic color cards in one request and checks the existing schema;
it never uploads private task media or enables app inference. It is not an accuracy
evaluation. Leave both flags false until the setup checks and consent are complete.
