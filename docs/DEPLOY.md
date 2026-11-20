# Hosted deployment (Vercel + Railway + Supabase)

Goal: a public URL where the team can run the full buyer → contributor →
verification → release workflow, redeployed automatically on every push to `main`.
Default mode is **fixture** (simulated funds, simulated AI result). Live Arc
funding and live Gemini stay disabled until their owners enable them deliberately
with the environment variables in `.env.example`.

```
Browser ──> Vercel (apps/web, Next.js)          auto-deploys from main
              │  NEXT_PUBLIC_API_URL
              ▼
           Railway service (deploy/railway/Dockerfile)   auto-deploys from main
              ├─ uvicorn framebounty.main:app   (API, $PORT)
              ├─ python -m framebounty.worker   (media verification, FFmpeg)
              └─ volume at /data                (uploads, shared by both)
              │  DATABASE_URL
              ▼
           Supabase Postgres (project ref scdivxechebsqtuupmij, us-east-1)
```

Why this split:
- Vercel only runs short-lived functions. The backend needs a long-running worker,
  FFmpeg and a persistent disk, so it runs on Railway.
- The API and worker share one container because uploads are local files and a
  Railway volume attaches to a single service. Moving media to object storage
  (e.g. Supabase Storage) would let them split later; that is a code change.
- Supabase is only the database. The app does not use Supabase Auth, Storage or
  its auto-generated REST API.

## 1. Database (Supabase): done

- Migrations run automatically: `start.sh` calls `alembic upgrade head` on every
  backend boot (idempotent). Current head: `0007`.
- Use the **session pooler** URL (port 5432), not the transaction pooler (6543):
  the app relies on row locks and prepared statements. The direct
  `db.<ref>.supabase.co` host is IPv6-only, so Railway cannot reach it reliably.
  ```
  postgresql+psycopg://postgres.scdivxechebsqtuupmij:<PASSWORD>@aws-1-us-east-1.pooler.supabase.com:5432/postgres
  ```
  `start.sh` also accepts the plain `postgresql://` form and adds the driver.
- **Security:** Supabase exposes `public` tables through its REST API using a
  public anon key. All tables have row-level security enabled and every
  `anon`/`authenticated` grant is revoked, including default privileges for future
  tables, so that API returns 401. The backend connects as the table owner and is
  unaffected. Re-check after migrations that create tables:
  `select tablename, rowsecurity from pg_tables where schemaname='public';`
- The password lives only in each developer's local `.env` (gitignored) and in
  Railway's variables. Reset it in the Supabase dashboard if it leaks.
- Local development can use the same database (no Docker needed). Automated test
  suites (`pytest`, `scripts/test_e2e.py`) still need a disposable Postgres via
  `TEST_DATABASE_URL`; never point them at the hosted database.

## 2. Backend (Railway)

1. New project → **Deploy from GitHub repo** → `framebounty`. `railway.json`
   selects `deploy/railway/Dockerfile` and the `/health` check. Auto-deploy on
   push to `main` is on by default for GitHub-connected services.
2. Add a **volume** mounted at `/data`.
3. Service variables:

   | Variable | Value |
   | --- | --- |
   | `DATABASE_URL` | Supabase session pooler URL above |
   | `APP_MODE` | `fixture` |
   | `FIXTURE_VERIFICATION_RESULT` | `pass` (lets the simulated flow reach release) |
   | `AUTH_ORIGIN` | the exact Vercel production URL, e.g. `https://framebounty.vercel.app` |
   | `STORAGE_ROOT` | `/data/media` (default) |

4. Settings → Networking → **Generate domain**, then check `https://<railway-domain>/health`.

`AUTH_ORIGIN` is both the only CORS origin and part of the signed sign-in message,
so it must match the browser origin exactly (no trailing slash). Vercel preview
URLs therefore cannot sign in; use the production domain.

## 3. Frontend (Vercel)

1. Add New → Project → import `framebounty`. Set **Root Directory** to `apps/web`
   (framework is auto-detected). Pushes to `main` deploy to production; other
   branches get preview URLs.
2. Environment variables (Production):
   - `NEXT_PUBLIC_API_URL` = `https://<railway-domain>`
   - optional `NEXT_PUBLIC_ARC_ESCROW_ADDRESS` = public V3 escrow address
3. Deploy. `NEXT_PUBLIC_*` values are inlined at build time, so redeploy after
   changing them.
4. Put the final Vercel URL into Railway's `AUTH_ORIGIN`; Railway redeploys.

**Repository access:** auto-deploy needs the Vercel and Railway GitHub apps to have
access to the repository. The repo is owned by a personal GitHub account, so only
that owner can grant it (install the apps on their account with access to
`framebounty`), or the repo can move to a GitHub organization the team shares.

## 4. Smoke test

Sign in with a browser wallet (MetaMask; message signature only), describe a task
as buyer, publish the simulated post, switch to Contributor workspace with a second
wallet/browser profile, reserve, upload a 10–30 s MP4/MOV or a JPEG/PNG (≥240px),
wait for "AI verified", then release as buyer.

Never put keys in `NEXT_PUBLIC_*` variables. Chain and model flags
(`ALLOW_CHAIN_TRANSACTIONS`, `ALLOW_MODEL_MEDIA`, `ALLOW_MODEL_TEXT`, allocator key)
belong to the on-chain/AI owners and are set in Railway only when they go live.
