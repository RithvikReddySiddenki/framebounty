# Workboard

Owner: implementation lead (Codex), branch `feat/framebounty-prototype`.
No concurrent editors have been identified. Shared interfaces are owned here until reassigned.

| Slice | Acceptance | Status |
| --- | --- | --- |
| Foundation | Reproducible shells, CI, plan/money rules and tests, state machine | c1e4406 pushed |
| Persistence/auth | PostgreSQL migrations, signed nonce, ownership enforcement | ab7a8e0 pushed; 62 backend tests and web checks passed; remote CI success verified |
| Escrow | Contract accounting/security suite and local integration | Contract implemented; 14 local-EVM tests pass, including two 256-run fuzz cases; application/Arc smoke integration pending |
| Collection | Funded search, confirmed atomic reservation, private mobile upload | Fixture search/reservation and authenticated raw phone upload implemented; real-chain reservation integration pending |
| Review/payment | Bounded verification, reviewer decisions, durable reconciliation | Leased PostgreSQL verification, real decode/sampling, private playback and human decisions implemented; live payment/reconciliation pending |
| Agents/export | Grounded tools, overlap-aware replanning, authorized dataset export | Role-scoped conversations/tools, durable intent retry, grounded search, confirmed reservation, next batches and private export implemented; live Gemini/evaluation pending |
| Live demo | Arc smoke, Gemini evaluation, real phone verification | Blocked on external setup |

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
