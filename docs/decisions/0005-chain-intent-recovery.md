# 0005: Durable signed intents and receipt verification

Context: broadcasting may succeed even if an RPC response or the worker process is
lost. A client-supplied hash and a pending transaction do not prove funding/payment.

Choice: persist intent, nonce, signed bytes and computed hash before server broadcast.
Retries reuse those bytes. Serialize signer nonce allocation in PostgreSQL. Verify
network, destination, sender, calldata, receipt status and exact escrow event before
recognizing a chain result. Keep unknown outcomes pending; do not silently release
an obligation because an RPC timed out. Models never receive keys or signing tools.
Local unlocked-account signing is permitted only against an explicit loopback test
chain; it is not a production/testnet credential mechanism.

Browser wallet retries need contract-level replay safety too. The MVP's confirmed
job has one fixed budget, so deposit is allowed once per job. Top-ups are deferred.
Refunds receive a unique job-scoped ID, preventing an old withdrawal intention from
spending funds released later by another reservation. These are deliberate ABI/policy
changes before any deployment, not assertion changes to hide test failures.

Alternatives: infer success from RPC submission, retry with a new nonce after timeout,
or fund/refund without unique identity. Rejected because each can duplicate effects
or display money that never settled. Existing single-payment reservation states stay.

Risks: the configured RPC remains a trust dependency. Fee changes and blocklist events
can leave outcomes pending rather than falsely failed. Local EVM evidence does not
prove Arc-specific native/token behavior; a funded Arc smoke remains required.

Validation: five real PostgreSQL/local-EVM tests cover saved-signature restart and
exactly-once payout, reverted/pending payment, unrelated wallet hashes/immutable
terms, and receipt-gated funding publication. The full contract suite now has 16
tests including deposit/refund replay protection and two 256-run fuzz cases.
Wallet UI recovery retains public hashes in session storage, and offers manual
hash entry if the wallet response was lost. Automatic event discovery and new
attempts after a verified revert are explicitly deferred; do not claim them done.
