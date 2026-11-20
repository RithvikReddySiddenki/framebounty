# Deployment preparation: Vercel + Railway + Supabase

This branch prepares configuration only. No projects have been created, deployed,
or billed by this work. Existing Vercel and Supabase accounts can be used later;
the owner still needs a Railway account. No hosting charges are authorized.

```text
Browser -> Vercel Next.js (apps/web)
       -> Railway API (direct authenticated uploads/downloads)
          + verification worker with FFmpeg
          + optional, explicitly enabled chain worker
          -> Supabase PostgreSQL (private framebounty schema)
          -> Supabase Storage (private framebounty-media bucket)
          -> /data persistent volume (operator gas ledger + decoder cache)
```

Keep hosted fixture/demo data separate from any real-USDC deployment. Start with
the fixture variables below and verify hosting before separately activating real
payments. Fixture AI results and funds are simulated; real FFmpeg/Pillow decoding
still runs. Circle Google login requires the setup in [CIRCLE_SETUP.md](CIRCLE_SETUP.md).

## Supabase preparation

1. Choose a project/region close to the future Railway region. This guide does
   not assume your existing project has been configured or migrated.
2. Review [bootstrap.sql](../deploy/supabase/bootstrap.sql), then run it in the
   project's SQL editor when deployment is authorized. It creates the private
   `framebounty` schema and private `framebounty-media` bucket. It does not move
   or delete existing app data. Do not expose this schema in Data API settings.
3. Copy the **session pooler** connection string from Connect. Use port 5432,
   `sslmode=require`, and the exact host/username shown by Supabase. Keep the
   password private and URL-encode reserved characters. The app accepts
   `postgres://`, `postgresql://` and `postgresql+psycopg://` forms.
4. Set `DATABASE_SCHEMA=framebounty`. Session pooling preserves the app's session
   advisory locks; do not substitute transaction pooling (usually port 6543).
5. Set `SUPABASE_URL` and the backend-only `SUPABASE_SECRET_KEY` (`sb_secret_...`)
   in Railway. Legacy `SUPABASE_SERVICE_ROLE_KEY` remains supported. New keys use
   only the `apikey` header, not a JWT bearer header. Never put either secret in
   Vercel or any `NEXT_PUBLIC_*` variable.
6. Keep the bucket private and give no anonymous/user policies for these objects.
   The app uses its own authenticated proxy, not Supabase Auth browser JWTs.
   Check existing project-wide storage policies if reusing a project.
7. Set bucket/project upload limits to fit your plan's allowed sizes. The app
   accepts up to 20 MiB per image and 100 MiB per video. Provider limits can be
   lower: verify actual account limits rather than assuming a free plan accepts
   every supported upload. Originals and model samples both consume storage.

The app checks private-bucket metadata before accessing objects. Cached files are
private decoder/download copies, not the only durable originals. Unpaid buyers
receive watermarked previews through the API; originals unlock after confirmed
payment. No public or signed Supabase object URLs are sent to clients.

## Railway configuration (do not deploy yet)

When authorized, create a GitHub-connected service with repository root `/`.
`railway.json` selects `deploy/railway/Dockerfile`. Review the integrated feature
branch first; do not switch production to an unreviewed branch automatically.
Also set `RAILWAY_DOCKERFILE_PATH=deploy/railway/Dockerfile` explicitly: the first
hosted CLI upload selected Railpack until this documented path override was set.

Use **one replica**, always running (no sleeping), and attach a persistent volume
at `/data`. The container supervises API and verification worker together; the
chain worker starts only with `RUN_CHAIN_WORKER=true` and matching chain consent.
If any process exits, the service exits so Railway can restart the whole group.
Do not run another operator signer against the same wallet/ledger elsewhere.

Copy names from [Railway env template](../deploy/railway/.env.example) into private
service variables. Required settings:

| Setting | Value |
| --- | --- |
| `DATABASE_URL` | Supabase TLS session pooler string |
| `DATABASE_SCHEMA` | `framebounty` |
| `AUTH_ORIGIN` | Exact HTTPS Vercel origin, without trailing slash |
| `STORAGE_BACKEND` | `supabase` |
| `SUPABASE_URL` | Your Supabase HTTPS project URL |
| `SUPABASE_SECRET_KEY` | Backend-only secret key (legacy service_role also supported) |
| `SUPABASE_STORAGE_BUCKET` | `framebounty-media` |
| `STORAGE_ROOT` | `/data/cache` |
| `APP_MODE` | `fixture` for initial hosted verification |
| `FIXTURE_VERIFICATION_RESULT` | `pass` (clearly simulated) |
| `ALLOW_CHAIN_TRANSACTIONS` | `false` |
| `ALLOW_MAINNET_TRANSACTIONS` | `false` |
| `RUN_CHAIN_WORKER` | `false` |
| `MAINNET_BUDGET_PATH` | `/data/operator/mainnet-budget.json` |

Startup validates hosted configuration/private storage, applies migrations, then
starts processes. `/health` is a minimal public liveness check; it is not proof
that Gemini, Circle or payments work. Review worker logs too. Each Python process
uses a small database pool; size the Supabase connection budget for all three.

Current single migration head is **0009**: camera is 0008, Circle is 0009. Our
Circle-only 0008 was tested solely in isolated schemas and never applied to the
active demo. If another developer manually applied that older feature migration,
stop and reconcile its schema; do not simply stamp it as camera 0008 or rerun
migrations blindly. Existing public-schema databases are not automatically moved.

## Vercel configuration

Set project **Root Directory** to `apps/web`. The local `vercel.json` selects
Next.js, `npm ci` and `npm run build`; use Node.js 22. Follow the public-only
[frontend env template](../apps/web/.env.example):

| Setting | Initial hosted fixture value |
| --- | --- |
| `NEXT_PUBLIC_API_URL` | Exact HTTPS Railway API origin |
| `NEXT_PUBLIC_ARC_CHAIN_ID` | `5042002` |
| `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING` | `false` |
| `NEXT_PUBLIC_ARC_ESCROW_ADDRESS` | Blank until the chosen deployment is verified |

These variables are embedded at build time; redeploy after changing them. Uploads
go directly to Railway, avoiding frontend function body limits. HTTPS is required
for the in-app camera. No Vercel API rewrite or frontend media proxy is needed.

Set Railway `AUTH_ORIGIN` to the exact final Vercel origin. The app intentionally
does not accept arbitrary Vercel preview origins. Use a dedicated staging backend
with a matching origin for preview testing; keep production data/keys separate.
Google OAuth redirect URIs must match that same frontend origin, as configured in
Google and Circle. Ensure each host's GitHub app has access to this repository.

## Readiness and later activation

After a separately authorized deployment, test two accounts: sign in, create an
image post, publish fixture funds, reserve, upload, verify, release, and export.
Repeat a video task using in-app recording. Restart the service and verify media
can be recovered from Supabase; verify anonymous/other-user access fails and
unpaid buyers cannot download originals. Fixture success is not a real payment.

To enable live models, configure Gemini/model consent flags in Railway. To enable
Circle, complete its account/Google setup and test returning-user login. Neither
requires putting provider secrets in the frontend.

Real USDC activation additionally requires a separate mainnet database/storage,
verified new escrow, funded dedicated operator, matching chain 5042 on frontend
and backend, and explicit mainnet/chain/worker flags. See CIRCLE_SETUP.md. The
existing 1-USDC deployment-and-initial-test allowance includes gas and reward;
hosting costs are separate and remain unauthorized. Never delete the persistent
operator ledger or move its signer to another instance to reset that allowance.

Local validation cannot prove provider accounts, quotas or live connectivity.
This machine has Docker CLI but no running Docker daemon, so an actual container
image build remains a pre-deployment check. Build from repository root later:
`docker build -f deploy/railway/Dockerfile -t framebounty-api .`

Official references checked for this preparation:
[Vercel monorepos](https://vercel.com/docs/monorepos),
[Railway Dockerfiles](https://docs.railway.com/builds/dockerfiles),
[Supabase connections](https://supabase.com/docs/guides/database/connecting-to-postgres),
[private storage](https://supabase.com/docs/guides/storage/security/access-control).
