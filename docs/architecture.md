# Architecture and implementation status

The repository starts with no application code. See workboard for implemented slices.
Target: Next.js UI -> FastAPI domain services -> PostgreSQL; durable jobs in PostgreSQL;
private storage adapter; bounded FFmpeg worker; Gemini observations; Arc escrow adapter.
AI proposals never authorize payments. Separate buyer/contributor tools call the same
authorized domain services as the UI. Review approval is a distinct human capability.

## External verification log (2026-11-16)

Arc configuration is intentionally **not pinned** until accessible official Arc/Circle
documentation and an RPC smoke check verify chain ID, RPC, explorer, faucet, token address,
ERC-20 decimals and native gas semantics. Attempts to access
https://docs.arc.network/arc/references/network-details and
https://docs.arc.network/arc/concepts/usdc-as-native-token failed in this environment.
Third-party search results are insufficient to authorize token transfer implementation.
Never copy an unverified address into runtime defaults. ERC-20 and native gas units must
be treated as separate external boundaries, even when both represent USDC.

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
