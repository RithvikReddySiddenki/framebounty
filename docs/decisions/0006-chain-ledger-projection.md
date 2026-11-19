# 0006: Pending obligations and receipt-gated ledger projection

Context: application budgets must stay solvent during slow allocation RPC calls.
An upload is not an on-chain submission lock, and human acceptance is not payment.
A process may die after receipt verification but before accounting updates.

Choice: atomically reserve slots/budget in `reserve_pending` before allocator
dispatch. A dedicated allocator signs only fixed reservation terms. Contributors
authorize their saved content hash; its verified event starts the canonical review
deadline and media queue. Human decisions become `accept_pending`/`reject_pending`.
The designated reviewer authorizes the fixed contract action in their own wallet.
Only verified receipts project payment, rejection, expiry or timeout into the ledger.

Migration 0005 snapshots fixture provenance and adds a durable `projected` flag.
The worker recovers confirmed/reverted unprojected intentions after restart.
Projection locks job then reservation/submission and commits accounting, terminal
state and flag together. Repeated projection cannot pay/release twice. Terminal
timeouts fence late media-worker completion. Models cannot access signing/review.

Alternatives: reserve after broadcasting, treat uploads as on-chain submissions,
or mark accepted work paid immediately. Rejected because they permit budget races,
miss canonical deadlines or display unconfirmed money.

Risks: allocator availability/gas can leave allocations held. Unsigned allocation
cancellation, fee replacement, automatic hashless recovery and application
close/refund controls remain deferred. Reverted payouts remain unpaid/committed
until valid release; they are not automatically retried with another nonce.
Direct external chain actions require reconciliation rather than trust in the DB.

Validation: real PostgreSQL/local-EVM/FFmpeg tests cover the synthetic-video path,
pending/reverted payment, receipt/projection restart, idempotent projection, human
rejection, expiry, timeout, concurrent claims and late-worker fencing. These do not
establish Arc-native semantics, physical phone UX or model/task-quality accuracy.
