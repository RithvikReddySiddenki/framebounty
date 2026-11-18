# Test matrix

## Current evidence (2026-11-17)

- Full backend: **115 passed, 13 skipped**, one upstream Starlette/httpx deprecation warning.
  The thirteen local-chain cases run in the separate gate below.
  Command: `python -m pytest services/api/tests -q -p no:cacheprovider --basetemp=.local/pytest-auth-dashboard-full-01 --junitxml=.local/auth-dashboard-backend.xml`
  with TEST_DATABASE_URL pointing to the isolated local PostgreSQL 18 instance.
- Real PostgreSQL/local-chain gate: **13 passed**, no skips. Deploys the actual
  escrow/test token on an owned ephemeral node, and uses real FFmpeg: restart /
  double payout, reverted/pending payment, receipt-gated funding, full synthetic
  upload/review/payment, confirmed-but-unprojected recovery, rejection, deadlines,
  concurrent pending claims, late-worker fencing, canonical deployment restart
  and signed-term tamper rejection.
  Command: `python scripts/test_chain.py -p no:cacheprovider --basetemp=.local/pytest-deployment-full-01 --junitxml=.local/deployment-chain-results.xml`.
- Escrow: **16 passed**, no skips, including two 256-run fuzz tests.
  Command: workspace-local Arc Foundry `forge test --root contracts --use <absolute-local-solc-0.8.24> --offline -vv`.
- Chromium: **6 passed** in the isolated browser harness, using real wallet signatures,
  PostgreSQL, API, Next.js, video decode/sampling and standalone worker. Funds/model
  observations are explicitly fixtures; video is a generated test pattern.
  Command: `python scripts/test_e2e.py` with TEST_DATABASE_URL configured.
  Covers anonymous gate, signature refusal, actual server logout/revocation,
  session expiry, wallet change/reload, and full buyer/contributor/reviewer flow.
  Phone layout has no horizontal overflow and the sign-in action is above the fold.
- Web production build passed, including TypeScript validation of the final export UI.
  Authenticated dashboard and separate contributor submissions views also build.
- Funding UI typechecks/builds; its actual Arc wallet transaction flow has not been
  browser-tested. The complete fixture browser regression still passes. Canonical
  ABI/runtime freshness passes `python scripts/export_contract.py --check`.
- Read-only Arc preflight confirmed chain ID 5042002 and ERC-20 USDC decimals 6.
  Command: `python scripts/inspect_arc.py`. No transactions were submitted.
- Live setup only: configured Gemini key authenticates for model listing/metadata;
  no generation was performed at that metadata stage. Allocator has 20 test USDC, with successful canonical
  faucet receipt verified against both native and ERC-20 logs without double count.
  After explicit approval, the persisted deployment was broadcast and its receipt,
  canonical runtime and token getter verified. Actual gas: 0.028299117 test USDC.
  See docs/live-validation.md. No funded collection/payout is claimed yet.
- New real-filesystem tests cover OS deployment locking, secret/flag preservation,
  existing configuration and recovery-file protection, and key-alone inference denial.
- After the user confirmed Free tier with billing disabled, one live synthetic-card
  Gemini smoke passed: gemini-3.5-flash-lite, schema valid, 2.954 seconds, task
  completion not passed. Command: `scripts/smoke_gemini.py` with both explicit smoke
  gates set for that process only. No private media or application model flag was
  enabled. This is not a physical-task accuracy evaluation. Arc deployment has
  separately passed after explicit user approval.

The final synthetic workflow additionally passed its targeted accepted-record
duplicate regression (1 passed, 10 deselected) using
`scripts/test_chain.py -k real_reserve_upload -p no:cacheprovider --basetemp=.local/pytest-workflow-duplicates-01`.
One intermediate chain run encountered a migration teardown error while migration
0005 was being edited during the run. Stable fresh-schema runs subsequently passed;
no assertions were removed or weakened.

| Requirement | Current files / evidence | Remaining limit |
| --- | --- | --- |
| C01–C09 | contracts/test/Escrow.t.sol: authorization, budgets, fixed recipient, double payout, failed token, reentrancy, cross-job isolation, timeout/refund, deposit/refund replay and randomized sequences; Arc deployment/runtime verified | Full funded Arc workflow pending |
| I06/I07 chain recovery/funding | test_chain.py + test_chain_workflow.py: durable signature and projection restart, pending/reverted payment, transaction/event verification, funded publication, real media and human-reviewed payout; test_chain_rpc.py: wrong network/token and malformed providers | Arc-native semantics, hashless recovery and fee replacement pending |
| B03/B06/B08/B12 | test_submission_flow.py + test_media.py: bounded raw upload, private access, hashes, actual malformed/valid decode, review expiry, durable lease fencing | Process timeouts are not a total native-worker memory ceiling |
| B07/B14 | Exact and perceptual review flags in worker; real decode/frame tests | Similarity threshold is heuristic, no false-positive/negative evaluation |
| B13 | Completion attestation and full-video watch required; invalid decode cannot be overridden | Synthetic orchestration tests are not a model/task-quality evaluation |
| B02/I08/I12 | test_planning.py + test_submission_flow.py + test_chain_workflow.py: overlap, accepted/pending distinction, commitments preserved, advertised slots counted, fixed budget | Real Arc deployment/evaluation pending |
| I06/I07 (media portion) | Real DB job leases, stale completion fencing, cross-wallet video/frame/export denial | Live provider retries/reconciliation not exercised |
| E01/E02/E03/E05 (fixture portion) | e2e/collection.spec.ts: buyer draft/simulated funding, phone viewport upload, authenticated playback, human review, next batch, manifest download | No physical phone, live model or blockchain payment |
| Export | Authorized manifest and streaming ZIP; ZIP contents match accepted media bytes in regression test | Downloaded data is outside subsequent access control |
| Agent roles B09/B10/B11, I09/I11 (fixture portion) | test_agents.py: 15 cases for grounded data, explicit confirmation, role/HTTP ownership, injection/outage handling, concurrent/restarted tool intents, same-wallet role context isolation, exact plan money | Live model accuracy and chain-backed actions not evaluated |
| Live/evaluation | Separately gated | No Gemini accuracy/latency evaluation, consented physical-task sample set, or funded Arc smoke |

The first contract attempt hit Foundry's removed `testFail*` naming convention;
the test was renamed without weakening its assertions. The browser flow initially
exposed a duplicate worker CLI entry point, then a Windows console encoding issue.
Both were fixed; the full browser command subsequently passed. The optional worker
container has configuration only and was not built or run in this session.
The privacy hardening regression exposed a duplicate GET route that shadowed the
reviewer-specific response; it was removed, and a route-uniqueness regression plus
contributor identity-redaction test now pass. Three further real-DB tests cover
concurrent worker claiming and terminal review-timeout fencing.

## Historical baseline (2026-11-16)

Actual persistence/auth run, 2026-11-16:
`$env:TEST_DATABASE_URL='postgresql+psycopg://framebounty@127.0.0.1:55432/framebounty'`
then `./.venv/Scripts/python.exe -m pytest services/api/tests -q -p no:cacheprovider --basetemp=.local/pytest-auth-01`:
**62 passed**, including six real PostgreSQL tests with migration upgrade/downgrade.
One upstream Starlette warning about the httpx test client; no skipped tests.
An earlier full run had 56 passes and six temp-fixture setup errors due to Windows
profile temp-directory permissions; fresh workspace-local temp storage resolved them.
An earlier malformed-media regression failed once and was fixed, not removed.
`npm run typecheck` and `npm run build` in apps/web: **passed**.
`npm install`: 0 reported dependency vulnerabilities at install time.

| IDs | Requirement / file | Evidence |
| --- | --- | --- |
| B01 (partial), C07 (off-chain only) | Exact money and closed plan schema; tests/test_domain.py | Passed |
| B02 (pure rules only), I12 (not integration) | Overlap and committed targets; tests/test_domain.py | Passed unit coverage only |
| HTTP shell | tests/test_http.py | Passed; invalid draft returns 422, health disables payments |
| B05 (EOA only), I07 (job reads only) | tests/test_auth.py, tests/test_postgres.py | Passed nonce/wallet binding, replay/expiry, concurrent login, cross-wallet job access |
| B09, B11, I02 (DB fixture only), I09/I10 (partial) | tests/test_postgres.py | Passed actual database search, equipment/time filters, confirmation, idempotency, race/budget protection |
| B04 (adapter only), B10 (assessment schema only), B13 (observation boundary only) | tests/test_verification.py | Passed malformed/timeout/429/500/incomplete provider responses; no live model calls |
| B06/B12 (helpers only) | tests/test_media.py | Passed path/header/hash/metadata limits and malformed-input regression; no real decoding run |
| C01–C09 | Solidity security/accounting | Not implemented; Foundry absent |
| B03–B14 remaining portions | Upload, durable processing, complete role tools, review/payment behavior | Not implemented |
| I01–I12 remaining portions | Chain-backed collection/review/payment/reconciliation/export | Not implemented; no local-chain integration evidence |
| E01–E06 | Browser workflow | Not implemented; build is not browser evidence |
| Model evaluation | Labeled held-out samples, recommendation evaluation | Not run; no consented videos or provider credentials |
| Arc smoke | Deploy/fund/reserve/submit/pay/reconcile/refund | Not run; no funded wallets or deployment |

Git: foundation c1e4406 pushed to the feature branch. GitHub connector transport
failed while fetching remote CI; local success is not a remote-CI claim.

The planned IDs are taken from PROJECT_BRIEF.md. Partial coverage never marks an
entire requirement complete. No local or mocked result proves Arc or Gemini behavior.
