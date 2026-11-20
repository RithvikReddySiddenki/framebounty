# Workboard

2026-11-20 Circle/mainnet integration (implementation lead, feat/circle-mainnet):
base origin/main 4e30c64 to preserve teammate redesign/evaluation work. User wants
Arc mainnet USDC, Circle Google login (email OTP optional) and existing wallets; total agent
deployment/initial-test spend capped at 1 USDC including fees. Circle account,
Google OAuth client and production credentials are not configured. No paid plans
or domain purchases authorized. Own network guards, Circle authorization bridge,
wallet UI, migrations, deployment budgeting and tests. Existing running testnet
preview and archived funded jobs remain untouched. Acceptance: Circle verifies
user-wallet ownership; no arbitrary transaction proxy, no cross-network
account/funding confusion; original receipt/idempotency rules still govern money;
no mainnet transaction before bounded costs and funded mainnet setup are known.

Implemented and locally verified: Circle Google/optional OTP user-controlled EOA
login, exact durable intent signing bridge, cross-network session/job pins,
migration 0008, explicit mainnet deployment selection and persistent operator gas
budget. Validation: backend 185 passed/24 separate-chain skips; local EVM 25 passed;
contracts 29 passed; Node 13 passed; Chromium 8 passed/1 funding-mode skip plus
separate funding-mode 1 passed; production build passed. Migration tested only in
isolated schemas. Existing running preview and database unchanged. Setup guide
docs/CIRCLE_SETUP.md and decision 0013 explain user account setup and remaining
live gates. Real Google/Circle login and real-USDC settlement remain unverified;
mainnet spend is zero. Contract milestone already pushed as 2954a04.

2026-11-19 buyer-agent timeout fix (implementation lead): API health succeeds but
the browser uses a 15-second timeout for 45-second model requests (up to two calls
for contributor ranking). Give agent-message calls a bounded longer timeout,
distinguish timeout from network failure, retain same-message retry identity and
remove incorrect instructions to change the message. Validate delayed browser
response, request error classification and production build. No migration, wallet
action, contract or funding changes.

Completed: agent-message requests have a bounded 120-second browser window while
ordinary calls remain at 15 seconds; timeout and network errors are distinct.
Buyer composer shows a waiting state and no longer tells users to change their
message. Nine Node tests and production build pass. Browser regression passed
after a simulated provider failure and a real fixture-API response delayed 16s;
the retry retained the same message/request ID. Live exact cat prompt returned a
20-image, 20-USDC plan in 10.11s after one transient provider error; simple provider
connectivity also succeeded. These probes saved no posts or media and moved no funds.

2026-11-18 protected marketplace (implementation lead, feat/framebounty-prototype):
user authorizes fixed publication deadlines and locked budgets, immutable task
terms, automatic settlement one hour after on-chain verification, paid-only
originals and watermarked previews, and counterparty-only on-chain reputation.
Own contract V3, ABI compatibility, API/worker projections, media authorization,
rating UI and tests. Preserve V1/V2 funded contracts and archived demo records.
Acceptance: no early refund/close on protected jobs, no unverified payment or
buyer veto, exact-once permissionless settlement after deadline, no unpaid
original/frame bypass, and one immutable vote per paid trade per participant.

Implementation complete in source: V3 contract (27 contract passes), verification
attestation/automatic settlement worker, pending-provider retry, paid-only media,
fixed-deadline confirmation, counterparty ratings UI/API and expired-budget refund.
Full chain gate 23 passed; three targeted cases subsequently passed including one
new refund case. Backend 162 passed; browser 7 passed plus separate funding-mode
case 1 passed; six publishing coordinator tests and final production build pass.
Contract milestone b775e1b and integrated API/UI milestone b46154d pushed. After
explicit approval resolved the initial auto-review rejection, migration 0007 was
applied and V3 deployed/runtime-verified at 0xe613799458201e41830a5be3da5c2a7d18140da0.
Actual native fee 0.048168687 test USDC versus cap 0.1392871. Owned preview services
restarted successfully; fresh demo has zero posts, archive retains four jobs.
The complete live funded V3 walkthrough and labeled AI evaluation remain pending.

Owner: implementation lead (Codex), branch `feat/framebounty-prototype`.
No concurrent editors have been identified. Shared interfaces are owned here until reassigned.

| Slice | Acceptance | Status |
| --- | --- | --- |
| Foundation | Reproducible shells, CI, plan/money rules and tests, state machine | c1e4406 pushed |
| Persistence/auth | PostgreSQL migrations, signed nonce, ownership enforcement | ab7a8e0 pushed; 62 backend tests and web checks passed; remote CI success verified |
| Escrow | Contract accounting/security suite and local integration | 16 contract tests; Arc deployment receipt/runtime verified; full funded Arc workflow pending |
| Collection | Funded search, confirmed atomic reservation, private mobile upload | Receipt-gated reservation and hash lock tested on local EVM; browser/phone Arc validation pending |
| Review/payment | Bounded verification, reviewer decisions, durable reconciliation | Human-reviewed receipt-gated payouts, restart projection and releases implemented/local-chain tested; funded Arc check pending |
| Agents/export | Grounded tools, overlap-aware replanning, authorized dataset export | Implemented; one free-tier synthetic Gemini smoke passed; physical-task/model evaluation pending |
| Live demo | Arc smoke, Gemini evaluation, real phone verification | Deployment passed; waiting for buyer browser-wallet setup and consented clip |

Canonical interfaces: `services/api/framebounty/domain.py` owns plan and atomic money rules;
`docs/state-machine.md` owns intended escrow transitions. Changes must update consumers/tests together.
No implementation or deployment is claimed by a Planned row.

Interface update: task/confirmation/reservation/ledger HTTP atomic amounts serialize
as decimal integer strings so browser JavaScript cannot lose integer precision.
Draft plan validation currently accepts strict integer atomic amounts. Plan version/hash
is immutable for each saved draft. PostgreSQL migration 0001 owns the initial schema.
Fixture reservation state names are separated from live states by the `fixture_` prefix.
Live reservation attempts return 503 until chain-backed commitments exist.

Environment: isolated workspace PostgreSQL 18 cluster available on 127.0.0.1:55432;
Compose documents portable PostgreSQL 16. Arc Foundry and solc installed in ignored
.local for Ubuntu WSL; verified portable FFmpeg/ffprobe installed. No
production credentials or real videos have been provided. User explicitly approved
feature-branch pushes to the configured GitHub repository on 2026-11-16.

2026-11-17 active slice: implementation lead owns private upload, PostgreSQL durable
verification queue, and reviewer workflow in services/api and apps/web. Acceptance:
authenticated owner upload, bounded real decoding, private media access, durable retries,
mandatory human completion review, idempotent fixture decisions, overlapping coverage/export.
Live payouts stay disabled until chain intent/receipt reconciliation is implemented.

Shared interface update: migration 0002 adds submissions and verification_jobs.
Submission states: queued, verifying, needs_review, invalid, fixture_accepted,
rejected, timed_out. Queue states: queued, leased, done, failed, cancelled.
Reviewer decisions cannot set paid. `payment_confirmed` stays false for fixtures.
Streaming exports include only accepted data and never expose storage keys.

07b4b15 pushed: escrow/private collection milestone; 80 backend tests, 14 contract
tests (two 256-run fuzz cases), one Chromium full fixture flow and web build passed.
Current slice: separate buyer/contributor conversation state, closed role-scoped tools,
grounded search, explicit reservation confirmation, auditable decisions and retry safety.
Implementation lead owns migration 0003 and agent API/UI interfaces. Required tests:
cross-session reads, role escalation, invented task IDs, model injection, no-match,
explicit confirmation and duplicate request recovery. No model may approve quality.

Agent implementation now passes the real-DB role/tool tests and the Chromium two-agent
fixture workflow. Migration 0003 adds immutable-role sessions and durable proposing /
prepared / completed / failed turns. Browser-facing proposed plan money serializes as
atomic strings, preserving values above JavaScript's safe-integer range. Canonical
ReservationIntent is shared by ordinary UI and contributor tools. Final wider gates
passed before the next feature-branch commit: 95 backend tests, production build,
and Chromium's complete two-agent fixture flow. Remote CI for 07b4b15 passed all
three jobs (API/browser, contracts, web), run 44128224384.

61c945f pushed: isolated role-scoped agents and exact browser money. Current slice:
durable signed transaction intents and verified receipts, tested against PostgreSQL
and an isolated local Anvil. Owner: implementation lead for ABI, migration 0004 and
chain adapters. Before wiring live actions, close wallet-retry gaps: a job has one
fixed-budget deposit, and each refund has a job-scoped unique ID. Update contract,
tests, canonical ABI and state-machine docs together. No Arc deployment exists yet,
so no deployed ABI migration is needed. Live signatures/funds stay explicitly gated.

Current implementation: migration 0004, canonical ABI/runtime export, durable server
signatures/nonces, exact receipt/event checks and owner-only wallet funding/publication.
Optional UI supports saved-job resume and existing-hash recovery; flags default off.
Acceptance against real PostgreSQL/local EVM: lost-response restart reuses signature,
pending/reverted payouts stay unrecognized, unrelated hashes fail, exact funding
publishes once. Remaining: live reservation/submission/review ledger integration,
automatic hashless event recovery, fee replacement, real Arc/phone/model validation.

Milestone gates: backend 107 passed / 5 separately gated skips; isolated local-chain
suite 5 passed (including wallet nonce reuse denial); contracts 16 passed with two
256-run fuzz cases; Chromium fixture workflow 1 passed; typecheck/production build,
canonical artifact check and pip dependency check passed. Previous commit 61c945f's
push CI succeeded, run 44147385497. Current funding UI's actual Arc transaction
path remains untested; fixtures and local EVM are not evidence of a funded Arc demo.

Active continuation: implementation lead owns live reservation/submission/review
projection in marketplace, submissions, chain_workflow and wallet UI. Acceptance:
reserve budget atomically before allocator dispatch; no upload before confirmed
reservation; content hash confirmed by contributor; reviewer decision precedes
wallet payout; only exact successful receipts update paid/released accounting.
Unknown chain outcomes retain obligations. Validate with real PostgreSQL/local EVM
and preserve the existing complete fixture/browser regression.

Implemented locally: `reserve_pending` atomic holds, dedicated allocator dispatch,
contributor content-hash confirmation, receipt-started review deadlines, human
accept/reject decisions followed by reviewer-wallet settlement, idempotent ledger
projection and expiry/timeout release. Migration 0005 records fixture provenance
and durable projection completion. The worker recovers the receipt/projection
crash gap. Coverage/export/replanning include settled testnet data. Local gates:
108 backend passes with 11 separately gated skips, 11 real-chain passes, fixture
Chromium regression and web typecheck/build pass. No Arc deployment/phone or live
Gemini evaluation is claimed. Close/refund UI, fee replacement, hashless recovery
and unsigned pending-allocation cancellation remain open. Additive migrations have
been applied to the task-owned local development database through 0005.

ab88134 pushed and remote CI passed (44186470014). Draft PR #1 created after the
user explicitly approved using existing Git authentication; the connector lacked
PR-write permission. Local setup helpers parse only documented environment keys
without evaluation/output and create a dedicated allocator without showing its
private key. Manual checks passed: literal dollar values survive loading, invalid
files reject atomically, key/address match, repeated setup preserves the existing
file, and live flags remain false. Local .env is ignored; credentials are not
committed. User still needs to add their Gemini key and faucet-fund the allocator.

Live setup verified: Gemini key authenticates for model listing, allocator address
matches its local key, and Arc receipt c58fb358...06ec198 transferred 20 test USDC
to it. Native/ERC-20 views are the same balance, not additive. Active slice: lead
owns durable, bounded deployment preparation/reconciliation and an explicit live
model smoke gate. No paid inference or private-media upload is authorized by merely
saving a key. Confirm account free-tier status before any generation request.

Prepared deployment: predicted address d9935557...2fca3b063, hash
0274c17a...a0ac67f9ee; maximum native fee 0.0820663 test USDC. Nothing broadcast:
automatic approval review requires explicit permission for this irreversible
testnet deployment, requested asynchronously. Model metadata for
gemini-3.5-flash-lite verifies generateContent and official image/structured
support; local model selection set with application inference flags unchanged.
The synthetic-only live smoke additionally requires confirmed free-tier billing.
Duplicate blank/populated Gemini entries in local .env were safely consolidated
without exposing or replacing populated secrets. New deployment locks, signature
checks and configuration-preservation tests pass. No deployed escrow or inference
success is claimed while these gates are pending.

User supplied an AI Studio screenshot confirming Free tier with billing not set up.
The explicit synthetic-only Gemini smoke then passed with gemini-3.5-flash-lite:
closed schema valid, synthetic task completion not passed, latency 2.954 seconds.
No private media or application inference was enabled. This is one negative smoke,
not a task-quality evaluation. Arc deployment remains unbroadcast pending separate
explicit approval; the screenshot did not authorize spending testnet funds.

User subsequently explicitly approved the testnet deployment. Transaction
0274c17a...a0ac67f9ee confirmed contract d9935557...2fca3b063; exact runtime and
token getter independently verified. Actual gas cost 0.028299117 test USDC, below
the approved 0.0820663 cap. Local escrow address saved; application live flags
remain false. Escrow balance zero: no job is funded yet. Requested the user's
separate buyer/reviewer public wallet and browser-wallet app for the interactive
funding check. Full public evidence and remaining steps are in live-validation.md.

Buyer uses MetaMask and their public address validates; read-only Arc balance now
exceeds the 20-USDC budget plus gas. Local interactive preview launched on 3000,
API on 8000, with allocator and media workers. Process-only testnet/chain/text
flags are enabled; media-provider flag stays false, and web process receives no
Gemini/allocator secret. API/page health HTTP 200 and no live listings before
funding verified. User must now sign in and authorize plan creation, allowance
and deposit in MetaMask. Fixture-only publish controls hidden in live mode;
typecheck, production build and full Chromium fixture regression passed. Owned
preview processes remain running for the active wallet walkthrough and must be
stopped at final task teardown. Unrelated .vscode files are preserved.

Active user-requested slice: mandatory sign-in for all product services, plus an
authenticated marketplace dashboard guided by Prolific's clear task terms,
Upwork's role-specific AI help and Linear's quiet hierarchy/navigation. Lead owns
default-deny API guard, logout/session expiry, dashboard API, web shell and E2E.
Public exceptions are sign-in challenge/login and minimal operational health;
API docs/schema are disabled. Acceptance: anonymous/expired/revoked sessions cannot
search, validate plans or use any product route; no workspace mounts pre-sign-in;
buyer/contributor/reviewer flows remain functional at phone and desktop widths.

Implemented: default-deny guard across all product routes, minimal public health,
disabled docs/schema, real token revocation, expiry/wallet/provider invalidation,
and a client sign-in gate that mounts no services before verified login. New calm
sidebar dashboard uses genuine DB counts; task cards emphasize reward/time and
contributors have a separate submissions view. Review/submission refreshes update
counts/status. No external font request occurs before sign-in. Validation: 115
backend passes (13 separately gated chain skips), 6 Chromium passes including the
complete collection workflow, typecheck/production build, desktop/phone screenshots
and live anonymous route checks. Source of design patterns and limits: decision
0008. The preview is updated; existing collections and on-chain state preserved.

Testnet agent text fix: allow real text proposals in testnet as well as live mode, retaining explicit ALLOW_MODEL_TEXT consent and independent media gating. Regression: 19 agent tests and full backend 119 passed / 13 separate-chain skips. No migration or financial interface changes.

Agent-led posting simplification (implementation lead): prompt -> generated post preview -> explicit approval/funding; auto-loaded post cards with server-derived publication status and a public task preview. Advanced terms/conversation controls move behind disclosures. Preserve human financial approval and video-only fulfillment until image scope is confirmed. Acceptance: a generated plan reaches a saved post without retyping fields; draft/open/unavailable states are distinct; ownership and receipt checks remain enforced.

Completed image/video agent-post slice: typed plans, image uploads/private access,
bounded decoding, post-specific Gemini checks with durable consent, image exports,
generic-video requirements, automatic post cards/status, one request/preview/approval
buyer flow and contributor-agent discovery. Validation: full backend 129 passed /
14 separately gated chain skips; chain 14 passed including image payout; production
build passed. Live Gemini synthetic plan/schema smoke passed. Decision 0009 records
interfaces, compatibility and remaining real-world validation. No migration or ABI
change. Real consented-task model evaluation and user-funded Arc payout remain pending.

Draft post rendering fix (implementation lead): namespace funding/review sibling keys by panel and post ID. Acceptance: opening an unfunded post emits no duplicate-key warning and selecting another post resets funding approval. Added a separate real-API browser gate with chain funding UI enabled; no wallet transactions.
Validated: targeted draft-post browser gate 1 passed; production build passed. CI now runs this gate with funding UI enabled alongside the standard fixture flow. No database or contract changes.

2026-11-18 conversational workflow (implementation lead, feat/framebounty-prototype): replace contributor equipment/time form with grounded chat intake and clarifications; buyer chat retains missing fields and previews only complete terms; combine publishing controls under one explicit approval. New owned chat endpoints reuse durable agent sessions/turns, with role isolation, request replay and concurrency checks. Preserve atomic reservation and receipt-gated settlement. Acceptance: missing count/time prompts instead of guesses; chat profile drives real listings; publishing needs fewer app clicks, while wallet signatures remain explicit.

Completed chat-first slice: removed contributor equipment/time form, added
persistent conversational facts and missing-field questions, one-click explicit
reservation, automatic pending-reservation checks, and one app approval for guided
wallet publishing. Evidence: 142 backend passed / 14 separate-chain skips;
14 real local-chain passed; 7 Chromium flows passed / 1 funding-mode skip;
separate funding-panel gate 1 passed; 6 publishing-coordinator tests passed;
production build passed; mobile/desktop chat screenshots inspected. Live Gemini
clarification smoke passed after transient provider 503s. Existing data and Arc
funding preserved. Decisions/interfaces: 0010. No migration or ABI change.

2026-11-18 contributor clarification fix (implementation lead): support explicit unlimited time as no time filter rather than requiring a numeric minute count; retain stated resources such as pets across messages. Acceptance: the reported cat -> phone -> infinite-time sequence searches real funded listings, and later numeric limits/resource corrections still apply. Affects chat intake, search's optional time filter and contributor summary; no financial-state or database migration changes.

Validated unlimited-time fix: 150 backend passed / 14 separate-chain skips,
7 Chromium passed / 1 separate funding-UI skip, production build passed. Live
Gemini confirmed explicit no-time-limit with cat and phone retained. Existing
stored chats recover these preferences on the next message. No wallet action,
funding change, migration or private media upload was performed.

2026-11-18 automated verification/release (implementation lead): latest user request supersedes manual quality-review UI. Reject a mandatory requirement failure at model-reported confidence >=80%; uncertain/provider failures retry. Human action is final batch funds release only. Reservation window capped at twice task estimate. Owner here for schemas/state changes/ABI/migrations. Preserve old funded escrows; test new rejection and batch-payment authority on local chain before any deployment.

Automatic verification/final release implemented and locally activated. Validation:
158 backend passes / 19 separate-chain skips; chain/deployment gate 20 passes
(19 chain plus one config guard); contract 19 passes; Chromium 7 passes / 1 separate
funding-UI skip; production build passed. Includes 79/80 boundary, contributor-visible
automatic rejection, bounded retry, automatic expiry, exact-once batch payment,
reverted-batch retry and old funded-escrow preservation. V2 deployed and independently
runtime/receipt verified at 0xea83a29db7486295b93318081447222481d0dbea; actual native
fee 0.034230105 test USDC versus cap 0.0991465. Migration 0006 preserved existing
balances and original funded-job bindings. New default collections use V2. Existing
V1 release requires its original per-submission wallet approvals; verifier rejection
budget releases at V1 timeout. Live smokes used generated media only; buyer keys never enter the backend.
