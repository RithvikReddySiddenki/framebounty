# 0002: Explicit confirmation and fixture isolation

Context: recommendations can become stale, and two contributors can claim the last
funded slot concurrently. A successful simulated action must never imply live escrow.

Options: frontend-only checks, optimistic updates without a shared budget lock, or
database locks with immutable confirmation terms and idempotent service methods.
Choice: confirmation -> job -> task locks, unique confirmation consumption and
wallet-scoped retry keys, with a five-minute confirmation expiry. Refresh locked rows
to avoid stale ORM identity-map values. Only explicit fixture jobs can reserve today;
live requests fail with 503 until on-chain commitments and reconciliation exist.

Rationale: all tasks spending one job's budget serialize at the same row. The UI
does not invent records or reserve merely because a recommendation was displayed.
Risks: this is database fixture accounting, not an enforceable chain obligation;
database commits must later be ordered around durable transaction intents/events.
Validation: real PostgreSQL migration up/down, simultaneous login/claim, cross-wallet
confirmation, changed terms, unfunded/closed/expired task, retries and HTTP ownership.
