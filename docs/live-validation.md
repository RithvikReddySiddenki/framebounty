# Live validation evidence

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
5. Human reviewer watches the full video, checks completion/categories and signs
   their decision. Verify the exact payout receipt, coverage, next batch and export.
6. Perform a physical-phone check and record actual results before review/merge.

Close/refund UI, fee replacement, automatic hashless recovery and unsigned pending
allocation cancellation remain open. Local-EVM tests do not establish all Arc-native
funding/payment behavior. Do not merge the draft PR merely because deployment passed.
