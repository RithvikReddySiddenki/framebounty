# Hosted demo validation — 2026-11-20

Frontend: https://framebounty.vercel.app

API: https://framebounty-api-production.up.railway.app

Vercel deployment `dpl_FXTihNGFNJFBdSrzHYcPCHD7vuQ4` built feature commit
`2cac1df`. Railway runs the API and verification worker from the Dockerfile at
`deploy/railway/Dockerfile`. Private Supabase schema/bucket bootstrap and migration
0009 completed against the new project. Existing local demo data was preserved.

## Evidence

The explicit hosted Chromium gate passed all three cases: PNG, JPEG and video.
Each case used the public frontend and actual hosted API, PostgreSQL, storage,
worker, decoder, authorization checks and ZIP export. No response interception
or local database mutation was used to make these tests pass.

- Separate ephemeral buyer/contributor wallets signed genuine login challenges.
- A labeled synthetic post was published with simulated funding.
- Contributor chat found the real hosted task and confirmed its fixed terms.
- PNG/JPEG bytes uploaded through the image picker.
- Video used Chromium's synthetic camera device and actual getUserMedia and
  MediaRecorder through the app's recording/review/submission UI. The server
  accepted the reservation-bound capture token and decoded the resulting video.
- The deployed worker completed verification and persisted samples to Supabase.
- Anonymous originals returned 401; unpaid buyer video originals returned 403;
  buyer previews were watermarked JPEGs and unpaid exports were empty.
- The buyer released simulated funds through the UI. Originals and valid ZIP
  exports then became available, with no real payment claimed.

From `apps/web`:

```powershell
$env:HOSTED_SMOKE_URL='https://framebounty.vercel.app'
$env:HOSTED_API_URL='https://framebounty-api-production.up.railway.app'
$env:PLAYWRIGHT_BROWSERS_PATH=(Resolve-Path ../../.local/browsers).Path
node node_modules/@playwright/test/cli.js test e2e/hosted.spec.ts --output ../../.local/hosted-smoke-results
```

Result: **3 passed** in approximately 1.5 minutes. Screenshots are in ignored
`.local/hosted-smoke-results`; each test attaches public job/submission identifiers.
The tests are skipped unless both hosted URLs are explicitly configured and abort
before creating posts if the authenticated API is not fixture mode or enables
payments. `npm run typecheck` also passed. Backend modern-key regression suite:
219 passed / 24 separately gated chain skips; targeted storage/hosting: 30 passed.

## Scope and remaining setup

This is a **hosted fixture demo**. Verification outcomes and money are simulated;
it is not a live Gemini quality evaluation, physical-phone camera check, real-USDC
payment proof or Circle Google-login test. Circle login and all chain/model flags
remain disabled; existing browser-wallet login works. Mainnet was explicitly
deferred by the user. Public health and auth configuration returned HTTP 200;
`real_money=false`, chain 5042002, `circle_enabled=false` were checked.

To enable Circle Google login later, add `https://framebounty.vercel.app` as the
Google OAuth web origin and redirect URI, configure its server credentials, enable
the integration and perform an actual user sign-in. No secret belongs in Vercel
public variables or Git.

Railway is on a trial, with measured resource usage below one cent at the check.
No paid subscription was activated. A requested $5 alert / $10 hard workspace
limit was rejected because Railway requires an active subscription for limits;
we did not upgrade merely to enable it. The approved $10 total hosting budget
remains a constraint. Continued hosting after trial/credits requires separate
review of plan/recurring costs; no unlimited recurring spend is authorized.

The first Railway attempt selected Railpack and failed; explicitly setting
`RAILWAY_DOCKERFILE_PATH` fixed detection and the actual cloud Docker build passed.
The Vercel CLI deployment route timed out on api.vercel.com; Git-backed deployment
through Vercel's authenticated official web API succeeded. Production tracks the
integrated feature branch, without merging main.
