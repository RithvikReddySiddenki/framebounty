# Escrow

`src/FrameBountyEscrow.sol` implements the documented reservation/review/refund state
machine with OpenZeppelin SafeERC20 and ReentrancyGuard. No deployment is claimed.
Only chain 31337 (local tests) and 5042002 (Arc testnet) are allowed. Arc requires
the documented USDC interface address and six decimals. All rewards are ERC-20
atomic units; gas uses a separate eighteen-decimal native interface.

```powershell
npm ci --prefix contracts
.\.venv\Scripts\python.exe scripts/setup_arc_tools.py
.\scripts\test-contract.ps1
```

The setup helper installs checksum-pinned Linux x86_64 Arc Foundry and solc 0.8.24
in ignored `.local`; Windows uses Ubuntu WSL. On Linux invoke the installed forge
with `test --root contracts --use "$PWD/.local/arc-foundry/solc-0.8.24" --offline -vv`.
The 14-test suite includes two 256-run fuzz tests, malicious token callbacks,
cross-job funding isolation, failed payment, timeout and close/refund races.
These tests use a real local EVM and a local test token. They do not establish
Arc's shared native/token balance behavior or a deployed testnet workflow.

Buyer/allocator reservations rely on the backend's authenticated, task-specific
confirmation policy. Quality approval trusts the fixed reviewer. An abandoned
review times out by releasing funds, not by automatically paying. No role setter,
arbitrary recipient override, upgrade mechanism or unbounded loop exists.
