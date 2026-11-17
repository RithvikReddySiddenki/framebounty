# framebounty
An AI-powered marketplace where labs and developers commission custom data, agents manage tasks and budgets, and contributors find paid work. Built on Arc with USDC payments, featuring a robotics data collection demo.

## Current status

Foundation only: Next.js development preview, FastAPI health/draft validation,
strict atomic money rules and overlap-aware coverage calculations. No wallet,
escrow, funded search, uploads or payouts are connected yet. The preview is
explicitly illustrative. See [workboard](docs/workboard.md).

## Local setup (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e './services/api[test]'
Copy-Item .env.example .env
docker compose up -d postgres
.\.venv\Scripts\python.exe -m uvicorn framebounty.main:app --reload
# In another terminal:
cd apps/web
npm ci
npm run dev
```

Open http://localhost:3000 and API docs at http://localhost:8000/docs.
PostgreSQL is prepared by Compose but is not used by this first shell.
No Gemini key or wallet is needed to inspect the preview.

## Checks

```powershell
.\.venv\Scripts\python.exe -m pytest services/api/tests -q
cd apps/web
npm run typecheck
npm run build
```

`scripts/check.ps1` runs those checks in sequence. Contract, integration, browser,
live model and Arc smoke suites are not implemented yet and are not covered by
this command. See [test matrix](docs/test-matrix.md), [architecture](docs/architecture.md)
and [state machine](docs/state-machine.md).
