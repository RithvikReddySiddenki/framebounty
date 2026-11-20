# Test matrix

Additional live hosted gate: `playwright test e2e/hosted.spec.ts --grep
'hosted two accounts'` passed (1 test), with buyer creation/publication entirely
through buyer chat UI and a distinct contributor discovering/reserving through
work chat. Exact job/task/identity bindings and private-editor denial verified;
typecheck passed. No live model or chain transaction, and no Google credentials.

2026-11-20 live hosted fixture gate: PNG, JPEG and actual in-app MediaRecorder
capture with Chromium synthetic camera all passed (3 tests, ~1.5 minutes) against
public Vercel frontend, Railway API/worker and private Supabase DB/storage.
Includes unpaid access gates and post-release ZIP originals. Typecheck passed.
New secret-key support: full backend 219 passed/24 gated skips; targeted storage
and hosted config 30 passed. See hosted-validation-2026-11-20.md for commands,
public URLs, test boundaries, trial budget and disabled integrations.

2026-11-20 final teammate/hosting integration on feat/circle-mainnet: main 081a5e3
(camera), feat/deploy 9cae3ca (container) and integration 745b4b8 (judge README,
state-accurate verification reasons) combined without unresolved conflicts.
Camera migration stays 0008; Circle is serialized as 0009 (single head).

- `PYTHONPATH=services/api python -m pytest services/api/tests -q --tb=short
  -p no:cacheprovider --basetemp=.local/pytest-integrated-final`: 210 passed,
  24 separately gated chain skips, one upstream TestClient deprecation warning.
- `PYTEST_ADDOPTS="-p no:cacheprovider --basetemp=.local/pytest-hosted-chain
  --tb=short" python scripts/test_chain.py`: 25 passed against actual local EVM.
- Arc Foundry `forge test --root contracts --use <pinned-solc> --offline -q`:
  passed all 29 contract cases; `python scripts/export_contract.py --check`: passed.
- `npm run test:publishing`: 15 passed; `npm run build`: production build passed.
- `python scripts/test_e2e.py`: 8 passed / 1 separate funding-panel skip.
  Funding-enabled `--grep 'draft funding and review panels'`: 1 passed.
- Linux `python3 scripts/check_hosted_startup.py`: fixture, optional chain-worker
  and invalid-config cases passed using the actual Bash supervisor.
- Nine storage regressions passed again after final bucket metadata hardening.
  Hosted HTTP is the simulated boundary; real PostgreSQL, private bytes, decoder,
  payment-gated downloads, watermark and export rules are exercised.

Docker CLI is installed but daemon unavailable, so no image build was claimed.
No hosted database migration, Supabase request, Circle login, deployment or real
USDC transaction occurred. Hosting configuration alone does not prove live
providers work. Original running preview/database and local editor changes remain.

2026-11-20 Circle/mainnet feature branch: `python -m pytest services/api/tests -q
--tb=short -p no:cacheprovider --basetemp=.local/pytest-circle-final-2` with real
TEST_DATABASE_URL and feature-worktree PYTHONPATH: 185 passed, 24 separate-chain
skips. `npm run test:publishing`: 13 passed. `npm run build`: passed. Standard
Chromium run: 8 passed, 1 separate funding-panel skip; funding-panel gate with
NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true: 1 passed. Contract suite: 29 passed,
including mainnet constructor admission and two 256-run fuzz tests. Read-only
Arc mainnet preflight verified chain 5042 and six-decimal canonical USDC.
No real Circle login or mainnet payment was performed; operator spend is zero.
Final separate local-EVM gate: `PYTEST_ADDOPTS="-p no:cacheprovider
--basetemp=.local/pytest-circle-chain-final --tb=short" python scripts/test_chain.py`
passed all 25 cases, including legacy escrow funding and release compatibility.
Default Windows pytest temp access failed; workspace-owned --basetemp resolves
that infrastructure issue. Browser harness must use feature-worktree PYTHONPATH
or it loads the older editable API installation instead of this branch.

Buyer timeout regression (2026-11-19): `npm --prefix apps/web run test:publishing`
passes nine Node tests (six wallet coordinator cases plus three API timeout/error
cases); production build passes. `python scripts/test_e2e.py --grep 'buyer retries
the same message'` passes one browser case: a simulated provider 503 retains the
message/request ID, then a fixture-API response delayed 16 seconds reaches the
post preview rather than the old 15-second network error. Live Gemini accepted
the reported cat-image request with count=20, media_type=image and budget_atomic=
20000000 in 10.11s after a transient provider failure. No post was saved/published;
this validates text planning/connectivity, not collection or verification accuracy.

Protected-marketplace evidence (2026-11-18, decision 0012): 27 contract tests pass
(including two existing 256-run fuzz cases). Full local chain gate: 23 passed
(22 chain cases + one config guard), including V1/V2 job binding, verification
receipts, automatic payment despite an unsigned buyer batch, signed ratings and
exact-once projections. Three subsequent targeted chain cases passed for automatic
payment, rating receipt handling and the newly added expired-post refund path
(one additional distinct case). Snapshot tests reset node time near wall time;
production deadline bounds remain unchanged. Backend: 162 passed / 23 separately gated chain skips. Chromium: 7 passed / one separate funding-mode skip, plus that
funding-mode case separately passed. Six publishing coordinator tests and final
production build passed. Media tests verify <=480px watermarks, metadata stripping,
no unpaid original/frame alias bypass, fixed confirmation deadlines, pending
provider retry and fixture exclusion from blockchain ratings. No real-task model
accuracy claim. After explicit user approval, V3 was deployed/runtime-verified on
Arc and migration 0007 activated. Actual native deployment cost: 0.048168687 test
USDC versus cap 0.1392871. See live-validation.md for receipt/address/runtime evidence;
a full live funded V3 walkthrough remains pending.

## Current evidence (2026-11-18)

Image/video posts: JPEG/PNG private upload/decode, type/size/animation rejection,
post-specific verification, consent enforcement, generic non-towel video criteria,
claimable post status, image ZIP bytes and an image local-chain payout are covered.
Live Gemini generated a 20-image cat/tree plan and failed a synthetic color card.
That smoke is not a labeled accuracy evaluation or a live Arc funded-job test.


- Full backend: **158 passed, 19 skipped**, one upstream Starlette/httpx deprecation warning.
  The nineteen local-chain cases run in the separate gate below.
  Command: `python -m pytest services/api/tests -q -p no:cacheprovider --basetemp=.local/pytest-final-release-backend-02`
  with TEST_DATABASE_URL pointing to the isolated local PostgreSQL 18 instance.
  Includes testnet agent coverage inspection with explicit text consent, denied
  calls without consent, and visible provider failures without fixture fallback.
- Real PostgreSQL/local-chain gate: **20 passed**, no skips (19 real-chain cases plus one deployment-configuration guard). Deploys the actual
  escrow/test token on an owned ephemeral node, and uses real FFmpeg: restart /
  double payout, reverted/pending payment, receipt-gated funding, full synthetic
  upload/review/payment, confirmed-but-unprojected recovery, rejection, deadlines,
  concurrent pending claims, late-worker fencing, canonical deployment restart
  and signed-term tamper rejection.
  Command: `python scripts/test_chain.py` with `PYTEST_ADDOPTS="-p no:cacheprovider --basetemp=.local/pytest-media-chain-03 --tb=short"`.
- Escrow: **19 passed**, no skips, including two 256-run fuzz tests.
  Command: workspace-local Arc Foundry `forge test --root contracts --use <absolute-local-solc-0.8.24> --offline -vv`.
- Chromium: **7 passed** in the isolated browser harness, using real wallet signatures,
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

Draft-post identity regression: 1 Chromium test passed with NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true using python scripts/test_e2e.py --grep 'draft funding and review panels'. Both funding/review panels render without duplicate-key errors, and selecting another draft resets its funding approval. This separate CI gate performs no wallet transactions. Production build passed.

Conversational intake: 13 PostgreSQL/grounding cases passed, including role/owner
isolation, exact replay, concurrent updates, missing-count/budget/time questions,
and refusing to interpret a budget number as an item count. The full suite above
includes these cases. The 7-pass Chromium flow now exercises short count/budget
answers and contributor time clarification with no equipment form. The one
funding-panel test is skipped in fixture UI mode and passes in its separate gate.

Publishing coordinator: 6 tests passed via `npm --prefix apps/web run test:publishing`.
The exact production coordinator advances three receipt-gated wallet steps and
preserves hash recovery across API failures, rejection, navigation, timeout and
revert. Wallet/RPC are the external test boundaries. Full local-chain gate:
`PYTEST_ADDOPTS="-p no:cacheprovider --basetemp=.local/pytest-chat-chain-final --tb=short" python scripts/test_chain.py` -> 14 passed.
Production build and desktop/mobile chat screenshots passed inspection.

Live Gemini text-only intake smoke: buyer request without count -> asks count;
short count answer -> asks budget; budget answer -> exact 20-image / 20-USDC plan;
contributor phone statement -> time remains missing. No job or transaction was
created. Initial provider 503s were followed by successful simple/schema probes
and this complete intake smoke. This is not evidence of real task accuracy.

Unlimited-time regression (2026-11-18): 150 backend tests passed / 14 separate-chain
skips; 7 Chromium cases passed / 1 separate funding-UI skip; production build
passed. The reported cat -> phone -> infinite-time conversation now retains the
cat and searches without a duration cap. A PostgreSQL test uses a 2000-minute
listing to distinguish no filter from a fabricated 1440-minute limit, recovers an
already-saved buggy profile from history, and verifies later numeric limits and
resource corrections. Live Gemini returned no_time_limit=true, minutes=null and
both cat/phone resources for the reported synthetic conversation.

Automatic verification/final-release evidence (2026-11-18): default AI-policy posts
reject mandatory failures at >=80% model-reported confidence, block low-confidence
or unavailable checks, and require only final buyer release for payment. Real
PostgreSQL/Pillow tests cover 79/80 boundaries, contributor-visible rejection,
retry exhaustion, release authorization/replay and the 2x task-time reservation cap.
Explicit historical human-policy fixtures remain legacy compatibility tests.

Final commands/results: full backend 158 passed / 19 separately gated chain skips;
`PYTEST_ADDOPTS="-p no:cacheprovider --basetemp=.local/pytest-final-release-chain --tb=short" python scripts/test_chain.py` -> 20 passed (19 chain plus one configuration unit case);
contract suite -> 19 passed including two 256-run fuzz tests. Chromium -> 7 passed /
1 separate funding-UI skip; verifies no review/consent checkboxes, automatic
contributor rejection with reasons, final release and automatic next-batch posting.
Production build passed. V1 funded-job binding, V2 atomic batches, automatic
non-paying rejection, deadline release, reverted-batch retry and restart projection
are covered against the actual local EVM. Live Gemini rejected a generated color
card at reported confidence 100; this is not real task-accuracy evaluation.

## Remove unfunded drafts (2026-11-20)

Owner-only removal archives unpublished zero-obligation drafts, including awaiting
escrow creation. Funded posts and unresolved deposit intents fail closed; bound
contracts are checked for zero funding history. PostgreSQL concurrency regression
serializes deposit intention creation against removal. Full backend 247 passed /
24 gated skips; final targeted draft suite 7 passed. Chromium creates a draft,
removes it through post details and verifies it stays absent after refresh.
Production typecheck/build passed. No chain cancellation/refund is implied.

## Fresh demo and streamlined authorization (2026-11-20)

Migration 0010 archives post visibility without altering immutable terms, balances,
reservations, submissions, media or transaction intents. Chats are archived and
app sessions revoked. Regression verifies an empty newly authenticated workspace,
revoked old sessions, inaccessible archived chats and preserved funded accounting.
Workers retain archived obligations for verification/release/settlement; new claims
and funding on archived posts are blocked. Circle users and chain history persist.
Upload now continues directly into its exact hash authorization using the existing
receipt coordinator; frontend regression verifies one signature and recovery after
a lost response without signing again. Browser suite: 12 passed / 5 gated skips;
frontend unit suite: 16 passed; build/typecheck passed. Migration-specific follow-up:
13 passed after updating the explicit single-head expectation from 0009 to 0010.
An entire folder still requires one Circle approval per image with current contracts.
Final full backend after migration expectation updates: 241 passed / 24 separately
gated chain skips. No failing assertions were removed or weakened.

## Folder and multiple-image submissions (2026-11-20)

Each image retains its own reservation, upload hash, verification and reward.
Contributor quantity selection is limited to advertised funded slots, with every
reservation still atomically checked by the server. Folder selection filters to
JPEG/PNG, lists the chosen images and permits a smaller count (up to 20). Chromium
tests cover reserving two slots, selecting a real folder with a non-image file,
uploading only one chosen image, using the remaining reservation later, and a
two-image upload interrupted on image two. Retry sends only the failed image to
the same reservation. Full backend 240 passed / 24 gated chain skips; full browser
regression 11 passed / 5 gated skips, followed by both folder/count/retry variants
passing. Frontend units 15 passed. These browser tests use explicit fixture money
and synthetic images; individual Circle hash authorizations remain required on
real Arc testnet, and no batch contract/gas sponsorship is claimed.

## Teammate frontend integration (2026-11-20)

Integrated main d7eb9bc with the current feature branch: dark/lime UI, consumer
dashboards, focused capture/review panels, contributor ordering of open tasks and
safe dead-Circle-challenge retries. Retained Google-only production access,
top-level Circle feeLevel, short-quote buyer grounding, private originals and
receipt-gated payouts. Full backend: 237 passed / 24 gated chain skips. Web units:
15 passed. Chromium: 10 passed / 5 gated skips; the separate funding-panel test
also passed with funding UI enabled. Production build/typecheck passed. Browser
media and money fixtures are explicitly synthetic; no new live payment proof.

## Buyer conversation evidence context (2026-11-20)

Live Gemini reproduced the reported defect: the exact complete towel-video
request yielded count=20 but evidence="20", which the old application discarded.
The fixed application chat path, with isolated PostgreSQL and actual Gemini,
returned a draft immediately for that request and for 20 cat images/20 USDC.
An incomplete dog-image request still asked for count and budget. Targeted chat
regressions: 23 passed, including preventing budget-derived counts and reuse of
historical bare answers as a new numeric field. These tests draft only; no
publishing, chain transaction or payment is implied.

## Google-only / actual testnet activation (2026-11-20)

Backend: 220 passed / 24 separate-chain skips. Web typecheck/build passed.
Chromium regression: 8 passed / 5 gated skips. New `circle.spec.ts`: 1 passed,
using the actual Circle SDK with an invalid OAuth state; safe code and retry are
visible. No successful Google sign-in is claimed. Live Gemini synthetic image
smokes correctly passed a requested red circle and failed a blue circle against
the red-circle request, both with model-reported confidence 100. Canonical V4
deployment receipt/runtime reconciled on real Arc testnet; hosted end-to-end
testnet payments remain a separate outstanding gate.

## Camera-only contributor capture (2026-11-20)

| Requirement | Evidence | Result / limit |
| --- | --- | --- |
| Video upload authorization | Real-PostgreSQL tests cover missing, foreign, expired, consumed and concurrent capture-token reuse plus unchanged image uploads | Full backend suite: 169 passed, 23 chain-gated skips; capture token is reservation/wallet bound and consumed transactionally |
| Browser media validation | `tests/test_media.py` covers MP4/MOV and WebM headers/codecs and bounded decoder failures | 25 passed |
| Camera helper behavior | `apps/web/tests/camera.cjs` plus existing publishing helpers | 14 of 14 web unit tests passed |
| Contributor UI | Playwright `buyer plan` flow stubs `getUserMedia`/`MediaRecorder`; covers denial/retry, no video file input, short rejection, review, retake and `X-Capture-Token` | 1 affected Chromium flow passed |
| Compilation | Web typecheck and Next production build | Passed; build required network access only for the existing Google Font fetch |

These deterministic tests do not prove a physical camera, real phone-browser
compatibility, camera authenticity, liveness, or remote HTTPS configuration. No Arc
transaction, deployment or live model call occurred for this slice.
