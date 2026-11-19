# Automatic verification and final batch funds release

The user's 2026-11-18 instruction replaces mandatory manual quality checks with
automatic verification. The only required buyer action after submission is final
funds release. Contributors still select work, supply media and authorize their
own content-hash commitment; publishing still needs wallet authorization.

Default plans use `verification_policy=ai`. Historical explicit `human` plans and
APIs remain for compatibility, not as the current UI flow. Previously stored plans
without the policy field use automatic verification without changing their saved
content/rubric hash. Every model criterion includes result, explanation, cited
samples and integer model-reported confidence. This is not a calibrated probability.

Mandatory criteria are task completion, visibility and the reserved task's target
categories. A failure at confidence >=80 is automatically rejected with reasons
visible to its contributor. Corrupt media is a deterministic rejection. Mandatory
passes at >=80 make a decoded submission `verified`, not paid. Low-confidence,
uncertain or unavailable-provider observations retry up to three times, then stay
blocked until the configured release timeout; they never silently pass or become
a confident rejection. Similarity flags remain informational.

The verification worker has no payout key. Escrow V2 allows the dedicated
allocator/verifier only to reject and free a submitted commitment. Only the
designated reviewer can pay. `approveBatch` atomically pays at most 20 immutable
reservation recipients/rewards, binding job, batch ID, membership hash, amount and
count in a verified receipt. Duplicate IDs, replay, wrong signer, expired work or
failed transfer revert the entire batch. A durable payout batch and transaction
intent protect retries; confirmed-but-unprojected receipts recover after restart.
The database records paid only after successful receipt recognition. Fixture
release is explicitly simulated and cannot represent a chain payment.

Reservation upload windows end at the earlier of twice Task.minutes, the listing
deadline, or the contract's seven-day maximum. Allocation/retries never extend
that deadline. Submission starts the separate funds-release window. Unused and
timed-out commitments release automatically from verified chain time. Workers
scan only due deadlines/rejections rather than polling every active obligation.

Existing funded contracts are immutable. Migration 0006 pins each job to its
original transaction destination and adds durable payout batches. The preserved
V1 artifact verifies old runtime exactly; it is not an arbitrary-code fallback.
Existing funds remain at V1. Its final release uses a guided sequence of original
reviewer transactions; it cannot gain a new atomic batch method. Rejected V1
commitments release at their original on-chain timeout. New V2 collections support
single-transaction batches and immediate verifier rejection. No escrow funds are
transferred or re-bound during an application/deployment upgrade.

After a confirmed final release, deterministic allocation publishes the next
small batch within the already approved budget, counting accepted data, active
obligations and advertised slots. No additional manual coverage check is needed.

The UI removes quality attestations and decision forms. Submission itself is the
explicit rights/AI-processing consent action, with a visible explanation. Optional
media inspection remains available. The final button shows the verified count
and reward amount. New-format payouts use one wallet signature; V1 explains its
per-submission signatures. Payout refusal/revert/unknown outcomes retain recovery
state and never claim success.

Evidence: PostgreSQL/Pillow threshold/retry/release tests, real local-chain batch
and automatic rejection/expiry tests, V1 funded-job preservation tests, 19 contract
security/fuzz tests and Chromium image/video flows with zero review checkboxes.
Synthetic fixture observations do not establish real-world model accuracy. Live
Arc deployment and user-authorized paid-task transactions are recorded separately.
