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
Live chain orchestration, payouts and provider evaluation remain pending.
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
The `.env` example documents settings; shell commands above explicitly export the
ones currently needed. The API does not automatically load `.env`. Do not put any
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
