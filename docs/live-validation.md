# Live validation evidence

## Protected marketplace V3 activation pending (2026-11-18)

V3 source/artifact and API/UI are tested locally (decision 0012 and test matrix).
Automatic approval review rejected pausing owned services, applying migration 0007
to the active demo database and preparing/deploying V3 because explicit operator
permission is required. The rejected command did not run. No V3 signed state,
broadcast or deployment hash exists. Default remains V2 at
0xea83a29db7486295b93318081447222481d0dbea. Existing V1/V2 funded jobs do not acquire
V3 payment/reputation guarantees. Read-only preflight found zero fresh-demo jobs
and no pending chain intents; original archived records remain preserved.

Read-only eth_estimateGas for exact V3 creation code: 2,313,119 gas; helper's bounded
limit 2,785,742. At that quote maximum native fee is 0.1392871 test USDC
(139287100000000000 native atoms, 18 decimals). No buyer budget is involved.
Quotes may change; the fixed helper caps still apply. Await explicit activation
approval before signing, migrating, restarting or changing the configured default.

## Arc testnet deployment

The user explicitly approved the prepared deployment on chain **5042002**.
The saved transaction was broadcast once and its receipt/runtime verified:

- Escrow: `0xd99355572a0a93f97254af3715300082fca3b063`
- [Deployment transaction](https://explorer.testnet.arc.io/tx/0x0274c17ae90bb87dbf2fdd2d25fdbe77fb89a6f1fcf163decb7bd2a0ac67f9ee)
- Actual native gas cost: **0.028299117 test USDC** (18-decimal accounting).
- Prepared maximum: **0.0820663 test USDC**.
- Runtime keccak256: `0x19aa00ec0d82c5cdb64adda80a41a52db84ad946fb651fa69a0fb124c70125e2`
- Immutable token/getter: `0x3600000000000000000000000000000000000000`.

The runtime matches the canonical compiled artifact with that token immutable.
A separate read-only ChainRPC check passed after the deployment CLI completed.
The verified address is saved in local ignored `.env`; signed bytes stay in
ignored `.local`. Escrow balance was zero at verification. **No collection is
funded and no contributor payment is claimed by this deployment.** Application
transaction and model flags remain disabled pending the interactive demo setup.

The buyer wallet was subsequently verified funded above the 20-USDC budget plus
gas. An interactive local preview now runs at http://localhost:3000 with process-only
testnet funding and free-tier text-agent flags enabled. Private-video Gemini uploads
remain disabled. Persisted `.env` defaults stay conservative. The API health check
and page return HTTP 200; live task search is empty before any buyer deposit.
Owned process metadata/logs are private under `.local`. Preview output uses the
ignored `.next-live` directory independently of browser-test caches. Fixture funding
controls are hidden in the live funding interface. This is readiness evidence, not
a claim that the buyer has signed or deposited funds.

## Gemini synthetic smoke

The user supplied an AI Studio screenshot showing Free tier and billing not set
up. One explicitly gated request sent generated synthetic cards only, using
`gemini-3.5-flash-lite`. Schema validation passed in 2.954 seconds. Task completion
was `fail`, towel/surface observations `uncertain`, and visibility `fail`.
This is a negative transport/schema smoke, not a physical-task accuracy benchmark.
No private videos were sent and application inference flags were not enabled.

## Remaining interactive checks

1. Buyer provides a public browser-wallet address distinct from the allocator and
   funds it with the intended contributor budget plus native testnet gas. A separate
   contributor wallet also needs gas to confirm its content hash.
2. Enable the verified testnet configuration and funding UI, then have the buyer
   authorize creation, exact allowance and deposit in their own wallet.
3. Contributor explicitly confirms a real funded task; allocator commits it on chain.
4. Contributor uploads a lawful/consented physical-task clip and confirms its hash.
   Private-frame model evaluation requires separate consent before enabling media.
5. Automatic verification checks the post requirements. A confident failure rejects
   with visible reasons; passing work waits for the buyer's final batch release.
   Verify its exact payout receipt, automatic next batch, coverage and export.
6. Perform a physical-phone check and record actual results before review/merge.

Close/refund UI, fee replacement, automatic hashless recovery and unsigned pending
allocation cancellation remain open. Local-EVM tests do not establish all Arc-native
funding/payment behavior. Do not merge the draft PR merely because deployment passed.

## V2 deployment and automatic verification (2026-11-18)

- Contract: `0xea83a29db7486295b93318081447222481d0dbea`.
- Transaction: `0xccf895f7185bcf4bcb6125affb3798b60ef708fa2fde8af9e8c2ed487e45ec0d`.
- Chain: Arc testnet 5042002; successful receipt and exact canonical runtime verified.
- Runtime keccak: `0x0f9cd999a6624e87be4b2895a1d91631d04ed20f16fa6135130cf3ede9595d33`.
- Native gas cost: 34230105000000000 atoms (18 decimals), or **0.034230105 test USDC**.
  The prepared maximum was 0.0991465 test USDC. No buyer escrow tokens moved.
- Migration 0006 applied locally with existing monetary ledger rows unchanged.
  All existing funded jobs retain their original contract binding.
- The signed V2 deployment remains in ignored `.local/arc-deployment-v2.json`;
  the original V1 signed record is preserved. An explicit previous-address guard
  was required to switch the default after confirmation; no replacement deployment
  or second broadcast was needed. New jobs default to V2; V1 funds stay at V1.
- Live synthetic image verification returned failure at reported confidence 100.
  This supports provider/schema connectivity, not a real-world accuracy claim.

A user-funded V2 collection-to-batch-payout walkthrough and labeled real-task AI
accuracy evaluation remain pending. Contract deployment alone is not that proof.
