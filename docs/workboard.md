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
