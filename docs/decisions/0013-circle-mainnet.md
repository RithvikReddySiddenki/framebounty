# Circle login and separate Arc mainnet operation

The user authorized real USDC, email-based access with optional existing wallets,
and at most 1 USDC total for deployment and the initial payment test. They have
no Circle account or sender domain. Google login through Circle is the primary
prepared path; email OTP remains configurable after sender-domain setup.

Use Circle User-Controlled EOA wallets: users authorize their own escrow actions,
while the backend verifies Circle wallet ownership before creating app sessions.
Client email and wallet addresses are not identity evidence. Existing wallet
accounts remain separate; no automatic linking by email. Circle user tokens stay
in memory and are never persisted by the application. Device redirect context
is tab-local and expires after ten minutes.

Circle transaction challenges bind to an existing exact transaction intent.
Provider success is only a candidate transaction hash: the established RPC
receipt, calldata, sender and event checks still establish funding/payment.
Persistent rate limits protect public login starts. Existing sessions and funded
jobs are pinned to their network; testnet assets never become mainnet balances.

V4 permits chain 5042 in the constructor and preserves all protected escrow
rules. V3 and V4 deployed runtimes are identical, so runtime verification treats
V3 as V4-compatible; original escrow bindings and payout tests remain intact.

Mainnet is explicit opt-in. Operator signing reserves maximum gas cost in a
locked durable ledger before signing; unknown results retain that allowance.
Verified receipts settle actual fees. This ledger covers operator gas, not
customer budgets: initial live-test rewards and customer gas must also fit the
user's overall 1-USDC allowance. No real funds have been spent or signed.

Validation includes real PostgreSQL ownership, quota, intent/retry and network
tests; actual local-EVM funding/payout compatibility; frontend build and browser
regressions. Live Google/Circle and mainnet payment proof remain external gates
until account configuration and the dedicated mainnet operator are available.
See ../CIRCLE_SETUP.md for reproducible setup and the test matrix for results.
