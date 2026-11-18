# 0007: Durable bounded deployment and explicit free-tier smoke

Context: the allocator is funded on Arc testnet and the Gemini key can list models.
These facts do not prove deployed runtime, inference correctness or free-tier billing.

Choice: persist deployment signature/hash/nonce before broadcast, under an OS lock
that releases on crash. Creation calldata is the canonical compiler output with
the configured token constructor. Check chain, token decimals, native balance and
gas caps before signing. Reuse saved bytes after uncertain outcomes; verify the
actual receipt, canonical block, CREATE address and exact immutable-patched runtime
before adding ARC_ESCROW_ADDRESS to local configuration. Preserve unrelated secrets,
flags and existing different escrow addresses. Keep signed state in ignored .local.

Deployment bounds: gas <= 3,000,000, fee <= 100 Gwei, hence <= 0.3 native test USDC.
The prepared current transaction has a tighter maximum of 0.0820663 test USDC.
No mainnet support exists. Explicit broadcast authorization is required by the
automatic approval reviewer in this session; preparation is not deployment.

Model listing/metadata are read-only setup checks. A synthetic-card inference smoke
requires ALLOW_LIVE_MODEL_SMOKE and GEMINI_FREE_TIER_CONFIRMED, following human
confirmation that project billing is disabled. No private video is uploaded. One
closed-schema negative smoke is not a task-quality evaluation and cannot approve
work. Application model flags remain off independently of the smoke flags.

Alternatives: deploy afresh after timeout, recognize code from a hash alone, or run
generation because a key exists. Rejected because these duplicate effects, skip
runtime verification or risk unauthorized paid inference.

Validation: real local EVM tests cover deployment response-loss/rebroadcast and
signed-term tampering. Native file-lock tests exclude parallel state owners and
allow reopening; filesystem tests preserve secrets and prior recovery files.
Arc broadcast remains gated pending the user's separate approval. After the user
confirmed Free tier with billing disabled, the synthetic negative inference smoke
passed (2.954 seconds, schema valid, task completion fail). Application inference
flags remain off; physical-task evaluation and private-media consent remain pending.

Current official references: https://docs.arc.io/arc/references/evm-differences.md
(native/token units and 20 Gwei floor),
https://aistudio.google.com/docs/models/gemini-3.5-flash-lite (image/structured
support), and https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite
(free-tier availability is distinct from this project's actual billing tier).
