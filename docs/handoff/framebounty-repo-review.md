# FrameBounty Repo Review
*Reviewed Thu Nov 19 · repo `RithvikReddySiddenki/framebounty`, branch **`feat/framebounty-prototype`** (HEAD `b86fd8d`, 27 commits, Nov 16–19). `main` only contains the README. Read-only review: nothing was run, installed or changed.*

---

## 1. TL;DR
- **This is a serious, well-engineered build.** It has a deployed escrow on Arc testnet, a FastAPI + Postgres backend, a Next.js frontend, buyer and contributor AI chat, automatic AI verification and on-chain payouts. It also has ~116 backend tests, 27 contract tests, 9 browser end-to-end tests and CI. It was built with an AI coding agent (Codex) from a detailed brief, which the rules allow ("AI tools encouraged").
- **The full live flow has never been run on Arc:** buyer funds → contributor uploads a real clip → AI verifies → USDC lands. Everything is proven on a local test chain with synthetic data. **This walkthrough is the #1 priority today.**
- **AI accuracy on real towel videos has never been measured.** The Gemini model isn't even set in config yet. That's your area (vision).
- **It differs from our PRD in a few places** (Gemini not Claude, MetaMask not Circle email login, a one-hour payment window, a contributor agent included). **Recommendation: keep his design.** There's no time to swap major pieces; rewrite the PRD and the pitch to match the build.
- **Submission gaps:** a judge-facing README (decision loop, safety limits, contract address), the demo video, Devpost answers, a few UX fixes, and getting the code onto `main`.

---

## 2. What he built

### Architecture
```
Next.js 16 web app (one page, Buyer / Contributor workspaces, MetaMask via window.ethereum)
        │  signed-session API calls
FastAPI + PostgreSQL (Alembic 0001–0007)
  ├─ chat.py / agents.py ........ Gemini buyer + contributor agents (role-scoped tools)
  ├─ worker.py (media worker) ... ffprobe/ffmpeg → 5 frames → Gemini verdict → policy
  ├─ chain_worker.py ............ allocator key: reserve / verify / settle / reject / expire
  ├─ payouts.py / refunds.py .... buyer early batch release, refund after expiry
  └─ reputation.py, previews.py . on-chain ratings, watermarked unpaid previews
Arc testnet: FrameBountyEscrow V3 at 0xe613799458201e41830a5be3da5c2a7d18140da0
```

### The user flow as built
1. **Buyer** signs in with MetaMask on Arc testnet and types a request in chat ("20 videos of towel folding under 20 USDC"). The Gemini agent asks about anything missing and drafts a plan. The plan is rejected if it doesn't match the stated count, type or budget.
2. Buyer publishes. **MetaMask signs `createProtectedJob`, then a USDC approve, then the deposit.** Budget, rubric and deadline are locked. The first batch publishes **2 slots**.
3. **Contributor** signs in with a *different* wallet and chats with their agent ("I have a large towel and a dark table"). The agent searches **real funded listings** and ranks them, and the contributor reserves with a two-step click. The **backend allocator key** records the reservation on chain.
4. The contributor uploads a 10–30 s MP4/MOV (or image), then **signs `submit(contentHash)` in their own wallet**. This needs gas.
5. **Media worker** extracts 5 frames (640 px) and sends them to Gemini with the post's criteria. Each criterion comes back as pass/fail/uncertain with a confidence of 0–100.
   - **Policy:** all mandatory checks pass at ≥80 → `verified`; any fail at ≥80 → auto-reject with reasons; anything else retries (up to 3 times, then every 5 minutes for protected jobs).
   - Duplicates (sha256 plus perceptual hash) are flagged only.
6. **Chain worker** calls `verify()`, which starts a **1-hour payment window**. After that, anyone can call `settle()` and the contributor is paid automatically. **The buyer can release early** (`approveBatch`, up to 20 clips in one signature). The buyer can't veto verified work.
7. After each confirmed payout, a **deterministic rebalancer** publishes the next ≤2 slots aimed at missing categories (e.g. large towel, dark surface), counting accepted clips, pending reservations and open slots.
8. **Extras:**
   - The buyer sees only **watermarked 480 px previews** until payment, after which the originals unlock.
   - **On-chain ±1 ratings** between buyer and contributor after payment.
   - **Refund** of unused budget after expiry.
   - **ZIP + manifest export** of accepted data.

### Safety design (good for the "agentic" judging story)
- **The LLM never moves money.** The agents can only use allow-listed tools: buyer `draft_plan / inspect_job / next_batch`; contributor `search_tasks / read_task / prepare_confirmation / reserve_task / my_work`. Reserving requires explicit user confirmation.
- Money actions are either **user-signed in MetaMask** (fund, submit, early release, refund, rate) or done by the allocator key under **deterministic rules** (reserve, verify, settle, reject, expire).
- **Contract-enforced limits:**
  - one fixed deposit, immutable recipients and rewards, no early refund on protected jobs, no self-trade
  - reservation expiry ≤ 2× the estimated time, batches ≤ 20
  - exact-once payments, no buyer veto after verification
- **Plan rules:** ≤ 20 items, total reward ≤ budget, 10–30 s videos.
- **Every transaction is checked:** destination and function selector are validated; receipts are matched against expected events; durable intents survive crashes.

---

## 3. Verified vs unproven

| Claim | Status |
|---|---|
| V3 escrow deployed on Arc testnet, runtime verified | ✅ Verified ([deploy tx](https://explorer.testnet.arc.io/tx/0x5fa53fe2a9d61756daada30a42dcf9d5361682f73c8a03c6a2c23f6f7cc0477b)) |
| Contract logic (27 Foundry tests, incl. fuzz) | ✅ Local EVM |
| Full app flow incl. payouts, rebalancing, export | ✅ **Local chain + synthetic data only** |
| Gemini connectivity and JSON schema | ✅ One synthetic smoke test (`gemini-3.5-flash-lite`) |
| Buyer chat plan from a real prompt | ✅ ("cat" prompt → 20-image, 20-USDC plan in ~10 s) |
| **Live V3 run on Arc: fund → reserve → submit → verify → pay** | ❌ **Never done** |
| **AI accuracy on real towel videos** | ❌ **Never measured** (`GEMINI_MODEL` not set; media inference flags off) |
| Phone upload over the network | ❌ Pending |
| Public deployment (URL) | ❌ Localhost only |
| Container/Docker runtime | ❌ Untested |

---

## 4. Differences from our PRD, and what to do

| Topic | Our PRD v2 | His build | Recommendation |
|---|---|---|---|
| AI provider | Claude Opus 5.5 | **Gemini** (model set by `GEMINI_MODEL`) | **Keep Gemini.** It's wired in with schemas, retries and consent gates. Swapping now is risk without reward. Spend the time picking the Gemini model and testing real clips. |
| Contributor wallets | Circle email-login wallets, no gas for contributors | **MetaMask**; contributor signs `submit` and needs gas | **Keep MetaMask** for the deadline. Pre-fund demo wallets. Mention "Circle email-login wallets" as the next step. |
| Payout | Auto-pay within seconds | Verify → **1-hour window** → automatic settle; buyer can release early | **Keep.** It's a stronger trust model (no buyer veto). **In the demo, use the buyer's early batch release** to show payment instantly, and explain the window. |
| Human role | Moderator backs up uncertain clips | No moderator; uncertain clips retry and stay pending | Acceptable. Say "uncertain → retried and held, never auto-paid". A moderator queue is "next". |
| Contributor agent | Cut | **Built** (search, rank, reserve with confirmation) | Keep. It's done, and it strengthens the agentic story. |
| Rebalancing | LLM proposes and a validator checks | **Deterministic** deficit-based next batch (≤ 2 slots) | Keep. Pitch it as "the agent observes coverage and commissions the gaps, by rules it can't break". |
| Extras not in the PRD | n/a | Watermarked previews, on-chain reputation, refunds, export | Keep; they're nice demo moments (especially reputation). |
| Circle tools for the Arc award | Wallets + nanopayments | Only USDC on Arc (no Circle SDK) | A weak spot for "Best use of Arc". Lean on **USDC as gas, the 6-decimal ERC-20 interface, atomic batch payouts, permissionless settlement**. Mention Circle wallets/Gateway as next steps. |

---

## 5. Gaps against the submission rules and demo
1. **Live end-to-end run on Arc** (blocking).
   - Needs two MetaMask wallets with testnet USDC: buyer (budget + gas) and contributor (gas for `submit`). Also a funded allocator key.
   - Needs these processes running: Postgres, API, media worker, chain worker, web.
   - Config: `APP_MODE=testnet`, `ALLOW_CHAIN_TRANSACTIONS=true`, `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true`, `ALLOW_MODEL_TEXT=true`, `ALLOW_MODEL_MEDIA=true`, and `GEMINI_MODEL` set.
2. **Real AI evaluation:** film ~10–20 real towel clips (pass and fail cases) and record accuracy and latency for the README.
3. **Judge-facing README on `main`.** The current README is developer setup plus caveats. It needs:
   - what and why, an architecture diagram
   - **the agent decision loop and safety limits** (track requirement)
   - **contract address + how Arc is used** (chain-award requirement)
   - how to run, and real results
4. **Merge the feature branch to `main`.** Judges will open the repo's default branch, which currently shows only a README.
5. **Demo video (2–3 min)** and **Devpost written answers.**
6. **Small UX fixes that matter on stage:**
   - Auto-add/switch MetaMask to Arc testnet (`wallet_addEthereumChain`). Today users must add the network by hand.
   - Stale copy: "complete towel fold required" shows on every post (reviews.tsx:274); the footer says "Buyer releases verified rewards" (workspace.tsx:263), which is wrong for V3.
   - Consent is implied (upload sends `rights_ack=true&model_ack=true` automatically). Add a visible checkbox.
   - Remove the dead `buyer-plan.tsx`.
7. **Deployed URL (optional):** the stack needs five processes plus ffmpeg, so hosting it in a day is risky. Plan to **demo live from a laptop** with the video as backup, and deploy only if time allows.

---

## 6. Plan for the remaining time (now → Fri 10 AM CST)

| Who | Today (Thu) | Tonight |
|---|---|---|
| **Rithvik** (knows the code) | **Run the live Arc walkthrough** with two wallets; fix whatever breaks; merge to `main` | Final rehearsal of the live demo |
| **Ayaan** (vision) | **Pick the Gemini model**, film 10–20 real towel clips (good and bad), run them through the verifier, tune the criteria wording, write an accuracy table | Supply clips and numbers for the README and video |
| **Teammate 3** | **Judge-facing README** (architecture, decision loop, safety limits, contract address, Arc usage) + **Devpost answers** | Final proofread |
| **Teammate 4** | **UX fixes** (Arc network auto-add, stale copy, consent checkbox); write the **demo script** | **Record the 2–3 min video** once the live run works |

- **Freeze at 9 PM Thursday.** Submit by **10 AM Friday**. Pre-fund all demo wallets and keep a recorded backup of the full flow.
- **Demo storyline:** buyer chat → plan → MetaMask funding → contributor chat finds the task → film a towel fold → AI verdict with reasons → buyer early-releases → USDC lands (explorer link) → coverage gap → agent commissions large/dark slots → ratings.
