# framebounty
An AI-powered marketplace where labs and developers commission custom data, agents manage tasks and budgets, and contributors find paid work. Built on Arc with USDC payments, featuring a robotics data collection demo.

## Current status

Implemented locally: signed EOA wallet login, buyer-owned versioned draft plans,
database-backed filtered task search, explicit version/reward confirmation,
atomic and idempotent fixture reservations, private reservation lists, strict
money/coverage rules, and bounded media/model adapter helpers. Fixtures are
clearly labeled and never represent real funds. Live escrow, upload endpoints,
review, payouts, agent conversations and exports are still pending.
See [workboard](docs/workboard.md).

## Local setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r services/api/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e './services/api[test]'
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
redeemable. No upload or payment is implied. Re-running seed creates another
fixture job; it never resets or deletes other users' data.

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
workspace directory. Contract, browser, live model and Arc smoke suites are not
implemented yet. See [test matrix](docs/test-matrix.md), [architecture](docs/architecture.md)
and [state machine](docs/state-machine.md).
