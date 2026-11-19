# Protected escrow, paid originals and counterparty reputation

The user authorizes automatic payment after a buyer payment window, superseding
0011's mandatory final human release. New AI-policy posts use V3 protected jobs.
V1/V2 bytecode artifacts and each funded job's deployment binding remain intact.

## Contract guarantees

The buyer signs a fixed rubric hash, publication expiry, task estimate and budget.
Default publication duration is 24 hours; task estimate defaults to 15 minutes.
Budget cannot close/refund before expiry. After expiry, only uncommitted money can
be refunded. Reservation deadlines are bounded by expiry and twice the estimate.
The UI displays a fixed deadline before acceptance, with a five-second allowance
inside that bound for block/server clock skew. Acceptance never extends it.

The dedicated allocator is also the trusted verification oracle. Passing checks
at the existing >=80 model-reported confidence policy are committed on chain with
an evidence hash. This starts a fixed one-hour payment window. Buyer batch release
can pay earlier; afterward anyone can call settle, with the app keeper doing so.
Recipients/rewards are immutable and transfers are exact-once. Buyers cannot veto
protected verified work. Rejected checks release only that obligation; provider
failure/uncertainty remains pending and retries in bursts with five-minute cooldown.
Unverified protected submissions do not time out into rejection or payment.
This can lock funds during a persistent oracle outage; it does not guarantee
service availability or correct AI judgments. Ethereum contracts need transactions
to execute: a worker outage delays settlement, but the permissionless method is
available directly to contributors/other callers. Reorg-safe receipt checks remain.

## Media

Original bytes are accessible to the submitting contributor and, after confirmed
payment, the buyer/reviewer. Explicit simulated acceptance remains fixture-only.
All original aliases and individual frame routes enforce the same boundary.
Before payment buyers get <=480px metadata-free JPEGs with repeated watermarks;
videos use sampled-frame previews, not original playable videos. ZIP/manifest
exports remain accepted-only. Watermarks discourage reuse but cannot prevent
screenshots, cropping, or AI removal. The server/storage operator still has access.

## Reputation

Each paid reservation permits one permanent +/-1 vote in each direction between
distinct buyer and contributor addresses. Third parties, self-trades, unpaid
reservations and repeat/change votes are rejected by the contract. Role-specific
up/down counts and vote events are public contract state, wallet-signed without
operator control. The UI displays raw counts rather than an invented trust score.
Votes are scoped to the particular escrow deployment; fixture and V1/V2 trades
cannot manufacture V3 reputation. Paid-trade eligibility does not prevent collusion,
Sybil wallets or retaliation. No personal text or media is written on-chain.

This decentralizes custody/settlement enforcement and vote persistence. AI
verification, search, authentication and private media storage remain service-owned.

## Validation

Protected.t.sol checks early close/refund, deadline bounds, self-trading, buyer
veto, unverified payment, exact payment boundary, expired-post obligations,
atomic batch release, failed transfers and immutable counterparty ratings.
PostgreSQL/media tests cover original/frame authorization, previews, exact
confirmation deadlines and provider retry recovery. Local-EVM workflow cases
exercise oracle receipts, automatic payment, buyer early release and signed votes.
See test-matrix.md for actual completed results; local tests are not Arc smoke
or measured model accuracy evidence.
