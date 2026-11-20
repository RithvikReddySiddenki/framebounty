# FrameBounty: Test Diagnostic and Change Rationale
*Thu Nov 19, 2026 · branch tested: `feat/framebounty-prototype` @ `b86fd8d` (Rithvik's latest) · run on Ayaan's Windows laptop, in a private review copy (nothing pushed)*

## 1. What I did and why

| Step | What I did | Why |
|---|---|---|
| Review copy | Cloned the repo into a scratch folder, read-only at first | Test Rithvik's real code without touching his GitHub or his working copy |
| Toolchain | Python 3.13 virtualenv, `npm ci`; portable FFmpeg, Arc Foundry and Playwright Chromium via **the repo's own setup scripts** (checksum-pinned) | Reproduce his CI as closely as possible, without installing anything system-wide |
| Database | Downloaded **official portable PostgreSQL 16.10** into a scratch folder and ran it on port 55433 | 80+ tests need real Postgres. **Docker Desktop crashes on startup on this laptop** (see §4), and portable Postgres needs no admin rights and leaves nothing behind |
| Test order | Unit → database → contracts → local chain → browser | Cheapest and most basic first, so a failure points at one layer |
| Fixes | Only small UX fixes from the PRD's P1 list, on a separate local branch `ux-fixes`, delivered as a **patch file** | Avoid colliding with Rithvik's ongoing work; the team decides whether to apply it |

## 2. Test results

| Suite | Command (from the repo) | Result |
|---|---|---|
| Backend (FastAPI, real Postgres) | `pytest services/api/tests` with `TEST_DATABASE_URL` | ✅ **162 passed**, 0 failed (22 skipped = the chain tests run in the suite below) |
| Smart contracts (Arc Foundry via WSL Ubuntu) | `forge test` | ✅ **27/27 passed**, including 2 fuzz tests × 256 runs (money is conserved) |
| Local chain integration (temporary local chain + Postgres) | `scripts/test_chain.py` | ✅ **24/24 passed** (~4.5 min): funding, reserve, submit, verify, settle, batch release, refunds, ratings, crash recovery |
| Web typecheck | `npm run typecheck` | ✅ Clean |
| Web unit tests | `npm run test:publishing` | ✅ 9/9 before → **11/11 after** (2 new tests) |
| Web production build | `npm run build` | ✅ Builds |
| Browser end-to-end (Playwright, real API, worker, FFmpeg) | `scripts/test_e2e.py` | ✅ **8 passed, 1 skipped**, both before and after the fixes (the skip is the separate chain-funding variant) |
| Deployed V3 escrow (read-only RPC) | `eth_getCode` on Arc testnet | ✅ Contract present at `0xe613…0da0`, chain `5042002` |

**Conclusion:** Rithvik's code is in good shape. Everything that can be tested without real wallets, real funds or a real Gemini key passes.

**Note:** CI pins Python 3.12; this laptop has 3.13, and everything still passed.

## 3. Changes made (patch: `framebounty-ux-fixes.patch`, 4 files, +88/−4)

### 3.1 MetaMask automatically adds and switches to Arc testnet (`apps/web/app/api.ts`)
- **Problem:** at sign-in, the app only *checked* that the wallet was on chain `0x4cef52` and otherwise showed "Switch your wallet to Arc testnet". Judges and new contributors would have had to add Arc to MetaMask by hand (RPC, chain ID, currency, explorer), which is the most likely place for a live demo to stall.
- **Change:** a new `ensureArcTestnet()` runs before the existing check.
  1. If the wallet is already on Arc, it does nothing (the original behavior).
  2. Otherwise it asks the wallet to switch (`wallet_switchEthereumChain`).
  3. If the wallet doesn't know Arc (error 4902), it adds it (`wallet_addEthereumChain`) with the verified parameters: chain `5042002`, RPC `https://rpc.testnet.arc.io`, explorer `https://explorer.testnet.arc.io`, native currency USDC with 18 decimals.
  4. **The original chain check still runs afterwards.** If the user declines, they see the same clear message as before, and nothing is signed.
- **Why it's safe:** it adds no new permissions, and the login challenge and signature are unchanged. Network changes after sign-in still sign the user out, as before.
- **Verification:**
  - **2 new unit tests:** a wallet without Arc is added and switched, then sign-in completes; a user who declines gets the Arc message and no signature request.
  - The first test **fails on the original `api.ts` and passes with the fix**, confirming it really tests the change.
  - The browser tests are unaffected (their fake wallet is already on Arc).

### 3.2 Outdated copy fixed
- `reviews.tsx`: **"complete towel fold required"** appeared on *every* post's requirements, including the cat-image demo. It now reads "Videos: X–Y seconds. Each submission is checked automatically against the requirements below."
- `workspace.tsx` sign-in footer: **"Buyer releases verified rewards"** was wrong for V3, where payment is automatic after verification. It now reads "Verified work is paid automatically from escrow."
- **Verification:** typecheck, build and all browser tests pass. No test asserted the old text.

## 4. Not done, on purpose

| Item | Why not |
|---|---|
| **Consent checkbox on upload** | Rithvik's browser tests **assert that the upload screen has no checkbox**, and decision 0011 says clicking Submit *is* the consent, shown with a visible notice. **Decided Nov 19: keep it as is.** Submitting with the visible notice stays the consent action, in line with decision 0011. |
| **Pushing or committing to GitHub** | You asked for no pushes. The patch is ready for Rithvik or the team to apply. |
| **Docker fix** | Root cause found: a corrupted leftover socket file from Nov 2025 at `%LOCALAPPDATA%\Docker\run\dockerInference` (Windows error 1920) crashes Docker's startup every time. You chose to leave it. Fix later by renaming `Docker\run` to `run.broken`. |
| **Live Arc paid flow / real AI accuracy** | Needs the team's funded wallets, allocator key and Gemini key, plus real towel clips. Still **P0** for Rithvik (live run) and Ayaan (clips + accuracy). |

## 5. How to apply the patch (Rithvik or anyone with the repo)
```bash
git checkout feat/framebounty-prototype
git checkout -b ux-fixes
git apply framebounty-ux-fixes.patch
cd apps/web && npm run typecheck && npm run test:publishing
```
Then commit, push, and merge as the team prefers.

## 6. Environment state
- **Portable Postgres:** stopped after testing. It can be restarted in seconds from its scratch folder if more test runs are needed.
- Docker Desktop: not running (it crashes on start, see above).
