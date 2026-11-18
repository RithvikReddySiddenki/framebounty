# Architecture and implementation status

See workboard and test matrix for implemented slices and validation evidence.
Target: Next.js UI -> FastAPI domain services -> PostgreSQL; durable jobs in PostgreSQL;
private storage adapter; bounded FFmpeg worker; Gemini observations; Arc escrow adapter.
AI proposals never authorize payments. Separate buyer/contributor tools call the same
authorized domain services as the UI. Review approval is a distinct human capability.

## Image/video posts and verification

See decision 0009. `Plan.media_type` defaults to video for legacy records and is
part of new immutable plan hashes. Typed upload paths share ownership, reservation,
content-hash, review and settlement rules. Still-image decoding and generic
post-specific AI criteria complement the existing bounded video pipeline. Both
operator enablement and per-submission consent gate external media verification.
AI observations never grant acceptance or payment. No migration/ABI change.

## External verification log (2026-11-16)

The old docs.arc.network pages failed. Its official documentation index redirects
to docs.arc.io. Current official sources successfully read:
https://docs.arc.io/arc/references/connect-to-arc.md and
https://docs.arc.io/arc/references/evm-differences.md.
They specify testnet chain ID 5042002, RPC https://rpc.testnet.arc.io,
explorer https://explorer.testnet.arc.io, and faucet https://faucet.circle.com.
USDC is one balance exposed natively with 18 decimals and by ERC-20 with 6 decimals;
do not add the balances together. Native gas and token amounts differ by 10^12.
The docs recommend Arc Foundry for protocol-specific simulation; ordinary local
EVM tests do not reproduce Arc's runtime. Blocklist failures can leave uncertain
transaction outcomes; never infer payment from a broadcast hash.
Fallback direct HTTPS retrieval subsequently succeeded for
https://docs.arc.io/arc/references/contract-addresses.md and
https://docs.arc.io/arc/tutorials/install-arc-foundry.md.
Official testnet USDC ERC-20 address: 0x3600000000000000000000000000000000000000.
Read-only live RPC confirmed chain 0x4cef52 (5042002), decimals 6, and a
gas-price snapshot of 25000000000 native atomic units per gas. This is not
a funded smoke test or a prediction of future gas prices. The official docs
describe a 20 Gwei fee-cap floor. Never treat these gas units as reward atoms.
`scripts/inspect_arc.py` reproduces the read-only preflight.
`scripts/setup_arc_tools.py` downloads the SHA-256-pinned official Linux x86_64
Arc Foundry v0.8.0-4 archive into ignored .local, executed through installed WSL.
No mainnet work or live payment has been authorized or performed.

Official Gemini model and pricing pages were read:
https://aistudio.google.com/docs/models and https://aistudio.google.com/docs/pricing.
They list multimodal models, but account access and free-tier eligibility have not been
verified. `GEMINI_MODEL` remains unset; live mode must fail visibly until configured.
Sampled-frame processing will precede native video integration. Free-tier data handling
requires consent; unpublished lab media must not be sent without permission.

## Planned security boundaries

Wallet nonce authentication binds domain, URI, chain, nonce, expiration and wallet.
Private media requires owner/reviewer authorization on each read, never public bucket URLs.
Atomic row locking plus unique idempotency keys prevent concurrent reservation overspending.
Reservation confirmation binds task/version/reward/recipient and expires quickly.
Model outputs use closed schemas and bounded quantities; media cannot modify policies.
Logs contain IDs rather than prompts, keys or private media.

## Implemented service boundaries

Wallet login signs a server-owned challenge binding URI, chain, address, random
nonce and five-minute expiry. PostgreSQL row locks serialize nonce consumption;
eight-hour opaque sessions are stored by SHA-256 digest, kept in browser memory.
Only EOA signatures are supported; ERC-1271 wallets, rate limiting and session
revocation are not yet implemented. Configure AUTH_ORIGIN before remote hosting.
Use HTTPS for any remote deployment; current setup is loopback development only.

Job reads require buyer/reviewer ownership. Authenticated search returns task terms, not
private records. Confirmation is bound to wallet/task/version/reward for five
minutes. Reservation locks confirmation, job, then task, refreshing locked rows;
unique confirmation and wallet/idempotency constraints enforce retry safety.
Real reservations are disabled; simulated rows cannot silently become live ones.

Media helpers validate private generated keys, supported container headers,
metadata, dimensions, duration, frame rate and decode timeouts. Authenticated raw
uploads create one immutable submission and leased PostgreSQL verification job.
FFmpeg performs bounded real decoding and five timestamped frame extracts; Pillow
reports brightness/edge metrics, ImageHash reports possible near-duplicates.
Similarity flags never automatically reject repeated actions. Review access is
limited to contributor, job owner and designated reviewer. Only the designated
reviewer may decide quality, with required full-video/task-completion attestations.
Fixture acceptance updates only simulated accounting. Submitted obligations survive
original upload deadlines; an explicit review-timeout path releases funds safely.
Streaming ZIP export contains accepted videos, hashes, reviewed tags and rights text.
GeminiFrames uses bounded inline samples, a closed result schema and visible
provider failures. It is connected to the worker but has not been verified against
the live API. Fixture mode produces explicitly uncertain observations without
sending media anywhere. Live media calls additionally require ALLOW_MODEL_MEDIA=true.
All observations still require human review. Native process timeouts are not a total
decoder memory cap; the opt-in resource-limited worker container is not yet tested.

## Logical agents

Product services now have default-deny authentication at the FastAPI application
boundary, including task discovery, plan validation, status and overview. Only
sign-in challenge/login and minimal liveness are public; docs/schema routes are
disabled. Logout revokes the current opaque session. The web app renders only the
sign-in screen before verification and clears all workspace state on expiry,
wallet/network/provider changes or a matching-token 401. See decision 0008 for
race handling, visual organization and remaining authentication limits.

Migration 0003 adds wallet-owned, immutable-role agent sessions and durable turn intents.
Buyer sessions may optionally bind one owned job; contributor sessions bind an explicit,
editable-before-creation profile. Session/turn reads are owner-only. See decision 0004
for the tool matrix and retry ordering. Both roles share the same Gemini transport;
model selection cannot bypass the domain services or invoke a quality/payment tool.
Contributor reservation is a separate explicit intention bound to task/version/reward.
The canonical ReservationIntent schema serves both the ordinary UI and agent tool.
Browser-facing agent plan money uses exact atomic strings; database/internal plans
keep strict integer atoms. Live text needs ALLOW_MODEL_TEXT=true, model and API key.

## Chain intentions and funding

Migration 0004 stores immutable action terms, unique signer nonces, private signed
bytes, transaction hashes and verified receipts. `transactions.py` serializes nonce
allocation using PostgreSQL advisory locks. Server broadcast retries reuse the
same bytes; pending/reverted transactions never constitute payment recognition.
The chain boundary checks network, exact canonical runtime (including token
immutable), token decimals, actual sender/destination/calldata, canonical receipt
block and every expected event field. The canonical ABI/runtime is exported from
the pinned compiler, packaged with the API and checked in CI.

`funding.py` authorizes only the saved job's buyer and derives all three actions
from the immutable plan: create, exact allowance, fixed-budget deposit. It publishes
a first batch only after all receipts and current escrow terms/accounting agree.
The endpoint is disabled unless explicitly in testnet mode with the chain flag;
its UI has a separate public build flag. No HTTP endpoint accepts arbitrary Action
objects or signing keys. A resumed browser submits the existing hash; automatic
hashless event recovery and fee replacement are pending. Reverted intents require
deliberate operator/user recovery rather than automatic repeat spending.

The isolated chain harness deploys the actual contract/test token and uses random
ephemeral local node accounts. Local signing refuses remote/non-local networks.
Canonical escrow deployment/runtime has now been verified on Arc testnet; see
live-validation.md. Full native/token funding/payment behavior and wallet UX on an
actual phone still need live validation.

Migration 0005 adds explicit submission provenance and a transaction projection
marker. Live claims hold application funds/slots before allocator dispatch. The
dedicated allocator signs reservations only. Contributor content locks and reviewer
decisions use their own wallets. The chain worker resumes receipt-confirmed but
unprojected work, then atomically updates states, accounting and marker under job /
reservation locks. No worker approves quality. Pending/reverted payments retain
obligations until a valid receipt-driven release. Accepted testnet records enter
coverage, bounded replanning and private export. See decision 0006 for limitations.

## Conversational intake and publishing (2026-11-18)

Decision 0010 adds owned chat sessions and grounded clarification over durable
agent turns. Missing required details stay missing until stated by the user.
Contributor facts feed deterministic funded search, with AI ranking restricted
to actual IDs. The UI restores the latest contributor conversation for the
signed-in wallet. One explicit posting approval starts guided receipt-gated
publishing, retaining required wallet signatures and durable public hash recovery.
No model holds signing keys or approves payment. No migration/ABI change.
