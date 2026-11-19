FrameBounty — master implementation prompt
Paste this document into Codex in the project repository. Place the companion AGENTS.md at the repository root and PROJECT_BRIEF.md in docs/ first.

You are the implementation lead for FrameBounty, an AI-managed marketplace for custom data. Build a working, understandable hackathon prototype on Arc testnet. Execute the implementation; do not stop at a plan. Follow AGENTS.md and keep docs/PROJECT_BRIEF.md accurate as implementation progresses.
Product goal
A buyer describes a dataset, confirms a concrete plan, and funds a fixed USDC budget. A contributor agent helps people find suitable work, understand requirements, and reserve tasks with permission. Contributors complete the real-world work and upload videos for the robotics demo. Automated checks assess submissions against an agreed rubric. An authorized buyer/reviewer approves accepted work. The system pays contributors from escrow, tracks dataset coverage, and commissions the missing examples using remaining uncommitted funds.

The product is a marketplace for custom data collection and annotation, with agents helping both buyers and contributors. Robotics is the demo customer, not a restriction on the product. Build one complete supported video workflow before adding other data types. Do not build a general freelancing platform.

Demo buyer request: "We need 20 videos of people folding towels, each 10–30 seconds, including at least five using large towels and five on dark surfaces. Keep contributor rewards under 20 USDC."

Demo contributor request: "Find tasks I can do at home in 20 minutes. I have a large towel, a dark table, and a phone I can prop up."

Treat total count, large-towel count, and dark-surface count as overlapping requirements: one clip may count toward all three. Define size/surface categories through buyer-approved descriptions and example references; do not claim to infer physical dimensions precisely from pixels. Use an illustrative fixed reward of 1 test USDC per accepted clip and a maximum of 20 clips, with gas/inference separate. Publish a small initial batch and allocate later work to remaining gaps. Do not count pending work as accepted or buy redundant work while sufficient matching reservations are active.
Required architecture
Prefer a small monorepo:
- apps/web: Next.js, TypeScript, accessible responsive UI.
- services/api: FastAPI, Pydantic, SQLAlchemy, Alembic, PostgreSQL.
- contracts: Solidity escrow and a Foundry-compatible test suite appropriate to Arc.
- docs: architecture, decisions, test matrix, project brief, demo instructions.
- scripts: reproducible setup, seed, checks, demo reset.
- .github/workflows: CI for frontend, backend, contracts, and integration checks.
Use private object storage through an adapter, with a local implementation for development. Use a durable database-backed job runner for verification and transaction reconciliation; do not introduce Redis/Celery unless the complexity is justified. Keep the model and chain behind narrow interfaces.

Default AI provider: Google's Gemini API through a configurable model ID. Confirm the currently available image/video-capable free-tier model from official documentation and the account before pinning it. Never hardcode assumed quotas or promise free production inference. Provide deterministic fake responses for automated tests and an explicit demo-fixture mode, clearly labeled. Real mode must fail visibly if credentials, quota, or service access are unavailable.

Use FFmpeg/ffprobe for bounded video metadata/probing and timestamped frame extraction, OpenCV/Pillow for sampled-frame checks, exact hashes for identical files, and ImageHash for potential near-duplicates across clips. Frame sampling is a heuristic and can miss actions between frames. Start with start/middle/end and bounded intermediate samples; use native video input only after confirming provider support and limits. A similarity flag alone must not reject separate clips of the same repeated task. Add MediaPipe hand detection only if useful after benchmarking; it is not a substitute for checking task completion. No liveness challenge, screen-recapture detector, or automated authenticity claim is required for MVP.

Arc is the only target chain. Before coding token transfers, consult current official Arc and Circle docs and record verified network configuration, chain ID, faucet, explorer, USDC contract/interface, decimals, gas behavior, and available tooling in docs/architecture.md. In particular, distinguish native gas units from the supported USDC token interface and amounts. Do not assume every interface uses the same decimals. Never invent addresses. Test real Arc-specific behavior with a small testnet smoke flow. Local-chain success is not evidence that Arc deployment works.

Do not add QuickNode Streams, Solana, bridging, voice, Grok Bot, or prediction markets. Keep these in the future-work section only.
User journeys and product quality
Buyer:
1. Enter a prompt.
2. Review/edit structured requirements, examples, rubric, budget, task prices, rights declaration, and review deadline.
3. Confirm a versioned plan; funding is required before tasks become claimable.
4. View confirmed funds, committed rewards, paid rewards, available rewards, category coverage, pending work, and review queue.
5. Approve/reject submissions with reasons, see payout status, export accepted data, and close the job/refund uncommitted funds.
Contributor:
1. Connect a wallet and authenticate with a server-issued signed nonce.
2. Inspect the task, reward, immutable rubric version, funding status, reservation expiry, and approval authority.
3. Tell the contributor agent your time, equipment, and preferences; receive recommendations grounded in actual funded task records and explanations of fit.
4. Confirm a specific task and reward before the agent reserves it. Upload a video, acknowledge requested usage rights, and submit. Upload from a phone is required; in-browser recording is optional after upload works.
5. See verification findings, review outcome, transaction state, and an explorer link after broadcast.
6. Receive the promised reward if accepted. Do not revoke a valid reservation or reduce its reward because another submission filled the quota.
Reviewer:
See the full video with playback, timestamped sampled frames, per-criterion results, possible duplicate clip pairs, model explanations, and an auditable approval/rejection action. Task completion is mandatory: the reviewer must confirm an actual towel-folding demonstration, not merely acceptable lighting or hands in frame. Verify reviewer authorization on the server and on-chain. Models do not possess signing keys.

Use a clean visual design with a coverage dashboard, spending ledger, upload page, and review queue. Provide loading, empty, retry, error, and pending-transaction states. Avoid showing "paid" before a successful confirmed transaction. Add keyboard access and usable mobile layouts. Explain uncertain checks in ordinary language.
Agent behavior and boundaries
Implement two logical agent roles with separate permissions, tool schemas, conversation state, and audit logs. They can share one model adapter and backend; no autonomous agent-to-agent negotiation or orchestration framework is required.

Buyer-agent loop:
1. Observe confirmed escrow state, accepted submissions, pending reviews, active reservations, and remaining requirements.
2. Use structured model outputs to interpret the request and assess visible video requirements.
3. Compute deficits and spending limits deterministically.
4. Propose a small next batch targeting unmet requirements; validate it in code.
5. Reserve funding and publish new work only when authorized and actually funded.
6. Record the observation, proposal, validation, actions, and resulting state.
Contributor-agent loop:
1. Parse explicit skills, equipment, availability, and preferences; allow the user to edit them.
2. Search actual open funded tasks using deterministic eligibility filters (state, deadline, remaining slots, equipment, expected time).
3. Rank eligible results and explain matches using facts from each task. Never invent jobs, guaranteed earnings, or skills the user did not provide.
4. Show task ID, reward, requirements, expiry, and review terms. Obtain explicit confirmation bound to that task/version/reward before reserving.
5. Recheck eligibility and funds atomically when reserving. On stale results or contention, explain the failure and offer updated alternatives.
6. Track only the authenticated contributor's reservations, submissions, and payments. Suggest another task only after rechecking availability.
Tool boundaries: buyer tools may draft plans, inspect owned jobs, and publish validated batches within approved policy. Contributor tools may search published tasks, read public requirements, and reserve an explicitly confirmed task for the authenticated wallet. Neither role can approve quality, change another user's job, transfer arbitrary funds, or access another user's private media. All actions go through the same service methods used by the ordinary UI.

LLM outputs are untrusted. Validate schemas, identifiers, quantities, criteria, prices, and tool arguments. Contributor text and media cannot change the rubric, authorization, destination wallet, or payment rules. Do not treat a model's self-reported confidence as a calibrated probability. Use pass/fail/uncertain per criterion and route uncertain work to review.

For MVP, AI recommends acceptance; an authorized human explicitly approves payout. The agent can allocate new tasks within the buyer-confirmed policy. Document this boundary honestly. Do not claim autonomous scientific verification.
Escrow and accounting requirements
Use integer atomic units and explicit decimal conversions, never binary floating-point money. Keep contract state authoritative for enforceable fund commitments and payments. The database is a recoverable application view.

Implement the smallest defensible contract covering:
- Deposit and funded-job identification.
- Authorized task reservation with an immutable reward, recipient, unique ID, and expiry.
- Binding a submission to its reservation; locking it for a documented review window.
- Approval/payment by the authorized reviewer, only once per reservation.
- Rejection/release and expiration paths.
- A documented timeout path for abandoned reviews; disclose the human trust assumption.
- Closure/refund of only uncommitted funds; closure must not erase valid obligations.
- Events sufficient to reconstruct funding, reservations, approvals, payouts, releases, and refunds.
Before implementation, write a state-transition table covering reservation expiry, submission, review timeout, approval, rejection, closure, and refund races. Choose explicit terminal states. Expiry alone is not a license to refund funds still committed to a valid submitted task. No unbounded on-chain loops over all submissions.

Use established contract libraries where suitable. Validate role, job, recipient, amount, chain, and state. Protect against replay, reentrancy, double payment, unauthorized refunds, mismatched identifiers, and fee/accounting mistakes. Off-chain quality approval remains trusted; escrow does not prove quality or guarantee a fair reviewer.

Persist transaction intent before broadcast, track submitted hashes, handle failed receipts and timeouts, and reconcile on restart. Retrying must not create duplicate payments. Verify network, contract, event, job, and amount before recognizing deposits. Never accept a client-provided transaction hash as funding proof without validation.
Build and git workflow
Inspect the repository, git status, remote, existing instructions, and test commands first. Preserve teammates' work. Start on a feature branch or isolated worktree. If the repository does not exist or push access is unavailable, continue local work and report the exact blocker.

The user authorizes regular pushes to the configured project remote on your feature branch. Push after each coherent, tested milestone. Do not push to protected/default branches, force-push, rewrite others' history, backdate commits, or manufacture activity. Commit real progress with clear messages; never claim a push succeeded without evidence. If credentials or the remote destination are missing, ask only for that information while continuing independent local work.

Suggested milestones, adaptable to existing code:
1. Repository setup, runnable app shells, documented design/state machine, CI.
2. Structured plans, validation, database schema, funding/task contract interface.
3. Contract implementation with security/accounting tests and a local integration flow.
4. Wallet authentication, confirmed funding, task search, atomic reservation, contributor video upload.
5. Verification pipeline, review actions, payment orchestration and reconciliation.
6. Buyer replanning, contributor recommendation/confirmed reservation tools, coverage accounting, export, and end-to-end flow.
7. Arc testnet smoke test, visual polish, evaluation, documentation, recorded-demo readiness.
For every milestone: define acceptance criteria; implement in a small slice; add meaningful tests; run affected tests and required gates; inspect the diff; update docs; commit; push; verify CI. A successful local command is not proof remote CI passed. Keep main releasable.
Required tests
Create docs/test-matrix.md mapping test IDs, requirements, files, and actual results. Include at least:

Contract/unit:
C01 unauthorized approve, reserve, refund, or role change fails.
C02 reservations cannot exceed deposited available funds.
C03 duplicate approval/payment and replay cannot pay twice.
C04 reserved recipient/reward/job cannot be changed at payout.
C05 release, rejection, expiry, review timeout, and close/refund obey the state machine.
C06 paid + refunded + escrow balance equals tracked deposits under the defined accounting model.
C07 zero, maximum, invalid, and decimal conversion amounts are handled correctly.
C08 malicious receiver/token and reentrancy cases where applicable to the actual interface.
C09 concurrent approval/expiry/refund orderings preserve obligations.
Use fuzz/invariant tests for amounts and valid operation sequences.

Backend/unit:
B01 prompt schema and invalid/over-budget proposals.
B02 overlapping quotas, active reservations, pending reviews, and unmet requirements.
B03 duplicate submission, idempotency keys, and retries.
B04 malformed model output, timeout, provider outage, and uncertain results.
B05 task authorization, wallet nonce replay/expiry, wrong wallet, and reviewer ownership.
B06 invalid MIME/content, oversized/decompression-bomb files, unsafe filenames, export access.
B07 duplicate detection flags changed-size copies without automatically rejecting distinct similar videos.
B08 late submissions, payout failure, and reservation expiry transitions.
B09 contributor filtering/ranking respects declared equipment/time and available funded jobs; no-match is valid.
B10 invented task IDs, prompt-injection tool calls, unauthorized buyer actions, and cross-user reads are rejected.
B11 reservation requires confirmation bound to the displayed task/version/reward; retries are idempotent.
B12 truncated/corrupt videos, unsupported codecs, excessive dimensions/duration/size, and decoder timeouts are bounded and fail safely.
B13 wrong/incomplete physical task never passes solely because format/quality checks pass.
B14 multiple clips of the same action are not all classified as duplicates; test exact copies and transformed variants separately.

Integration with real PostgreSQL and local contracts:
I01 funded job -> reservation -> upload -> review -> payout -> export.
I02 simultaneous claims for the last task cannot oversubscribe budget or slots.
I03 transaction broadcast followed by process restart/retry yields one payment.
I04 failed/pending/reverted transaction never displays paid.
I05 wrong-chain, wrong-contract, or unrelated funding event is rejected.
I06 durable verification retry does not duplicate submissions or approvals.
I07 permissions prevent buyers/contributors reading or mutating unrelated private resources.
I08 replanning does not cancel promises or exceed available funds.
I09 search -> recommendation -> explicit confirmation -> reservation -> video submission persists identity and terms.
I10 a job filling/expiring between recommendation and reservation fails safely and refreshes results.
I11 two logical agents cannot use each other's privileged tools or leak private session data.
I12 reviewed clip tags update overlapping quotas once, and replanning accounts for both accepted and committed work.

Browser/E2E:
E01 buyer plan and funding flow.
E02 contributor search conversation, real task cards, confirmation, mobile video upload/playback, and status.
E03 reviewer approval, transaction progression, and coverage update.
E04 visible recovery from model/RPC errors.
E05 complete two-agent flow with labeled deterministic fixtures plus a separately documented real-provider smoke test.
E06 no matching work, stale recommendation, rejected camera permission if recording exists, upload failure, and pending review have usable UI states.

Model evaluation:
Create a small consented/lawful labeled sample with completed towel folds, incomplete/wrong actions, large-towel/dark-surface examples, duplicate/transformed clips, blur, occluded hands, and ambiguous cases. Separate threshold-tuning samples from held-out samples. Record false accepts, false rejects, uncertain rate, latency, and sample size. Evaluate contributor recommendations against a small manually labeled set of tasks/preferences for eligibility and explanation accuracy. No accuracy claim without results. No live provider calls in ordinary unit tests. A mocked provider validates orchestration, not model quality.

Arc smoke:
With test funds only, verify deploy, fund, reserve, submit/lock, approve/pay, reconcile, and refund. Record actual addresses and transaction hashes. External-service skips must be visible; never describe skipped tests as passed.
Documentation and completion
Write helpful comments throughout non-obvious code: function contracts, state transitions, money units, authorization boundaries, retry/idempotency logic, concurrency protection, and model limitations. Explain WHY and assumptions, rather than narrating every assignment. Add short decision records explaining alternatives and tradeoffs judges may ask about.

Expose reproducible commands such as make dev, make test-unit, make test-integration, make test-contract, make test-e2e, make check, and make smoke-arc (or equally clear equivalents). Define precisely what each command runs. CI should run deterministic checks without production secrets.

At the end report:
- Implemented functionality versus fixtures, partial work, and deferred features.
- Exact test commands/results, external smoke evidence, and unresolved failures.
- Branch, commits, push/CI status.
- Setup and demo instructions.
- Security/trust limitations and architecture decisions.
- Honest evaluation results.
  Never fabricate transactions, users, measured improvements, test results, or deployments. If blocked externally, finish independently testable work and state the blocker precisely.
Demo acceptance script
Create one real funded robotics request and several clearly labeled seeded task listings for search testing. The contributor agent must search database records, not return hardcoded task prose. Show a phone video upload, an unsuitable submission routed to review, a valid clip approved and paid, and the buyer agent commissioning an unmet category. Demonstrate that existing commitments survive replanning and a repeated payout cannot pay twice. Use a fixed phone support so both hands and the towel remain visible; do not require a head/chest mount or call an ordinary tabletop recording egocentric footage. Confirm decoding on the actual demo phone/browser.

Keep the product name FrameBounty. Do not rename it Groundtruth or copy the teammate proposal's automatic payout, mandatory liveness, embedded-wallet, x402, or provenance-proof claims. The current agreed scope is two agent roles, custom data work, a robotics-video demo, human quality approval, Arc, and USDC.
Implemented extension (2026-11-17): the marketplace now supports image and video
post types. The buyer agent generates the actual requested subject and observable
criteria; contributors can submit still JPEG/PNG images or bounded MP4/MOV videos.
Automatic post-specific AI observations require explicit contributor consent and
operator enablement. The human reviewer remains the payment authority. Decision
0009 and the test matrix record evidence and limits; the original robotics example
is no longer the only supported post subject.

User-authorized workflow update (2026-11-18): manual quality checks are removed.
Default image/video posts use automatic verification; a mandatory failure at
>=80% model-reported confidence rejects with contributor-visible reasons, while
uncertain/provider failures retry and cannot pay. The buyer's sole required
post-submission action is final batch funds release. New reservation upload
windows are capped at twice estimated task minutes. Decision 0011 supersedes
older manual-review requirements; signing-key and receipt/payment invariants remain.

User-authorized protected-marketplace update (2026-11-18): new posts lock their
budget until publication expiry and freeze agreed requirements. Reservations are
bounded at twice task estimate and show exact terms/deadline before acceptance.
After on-chain AI verification, buyers can release a batch immediately; after a
one-hour window anyone may execute the fixed payment. This supersedes mandatory
buyer final authorization for new protected posts. Provider failures remain pending
with automatic retry. Buyer originals and exports unlock after confirmed payment;
unpaid previews, including frame routes, are reduced and watermarked. Add mutual
on-chain up/down reputation, restricted to counterparties on paid submissions.
Decision 0012 records guarantees, oracle/availability trust and legacy compatibility.
