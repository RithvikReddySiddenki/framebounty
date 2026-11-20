# Contributor ↔ buyer matching

## Problem

On the hosted app a buyer publishes "a person pouring water into a cup". A contributor on another
computer says "I have a cup and no time limit" and the work agent answers "No matches."

Root cause:

1. `marketplace.search_tasks()` returns a task only when `Task.equipment ⊆ contributor equipment`,
   and also filters by minutes.
2. `planning.create_batch()` adds `phone` to every task, fixture and testnet alike.
3. In fixture mode the chat agent never calls Gemini and recognizes only 7 equipment words, so
   "cup" maps to nothing.
4. The buyer's title and requirements are never compared with what the contributor says.

Switching the hosted app to testnet alone does not fix it: Gemini only re-filters the output of
step 1, which is already empty.

## Approved scope

- Contributors always see every open, funded task in the current mode, ranked best match first.
  "No matches" only happens when nothing is published.
- Recording happens in the browser camera, so the recording device is not a matching requirement.
- Time is ignored: not asked, not extracted, not filtered.
- The agent asks one question ("What do you have on hand?") and then shows the ranked list.
- Gemini decides the ranking (synonyms such as cup ≈ mug ≈ glass are its job).
- The hosted app moves to Arc testnet so Gemini runs.

## Approaches considered

1. **Gemini ranks the full list at search time (chosen).** One structured call ranks every open
   task with a short reason. The server validates IDs and falls back to default order. No migration.
2. **Word-overlap score, Gemini re-ranks the top.** Works without Gemini, but needs a hand-kept
   synonym list, and the user chose Gemini for matching.
3. **Tag tasks at publish time.** Fast deterministic search, but needs a backfill and two prompts in
   sync, and a missed tag hides the task again (the same failure as today).

## Task 1: backend search and ranking

Acceptance:

- `planning.create_batch()` no longer adds `phone`. Towel posts keep `towel` / `dark_table`.
- New `marketplace.open_tasks(db)` returns every open, unexpired task with free slots and enough
  reward left, in the current mode (fixture flag and chain ID filters kept), ordered by deadline,
  capped at 25.
- `search_tasks()` becomes `open_tasks()` plus the existing equipment/time filter, so the older
  agent-pane path (`agents.py`) and its tests are unchanged.
- New `chat.rank_tasks(...)`:
  - Gemini gets the contributor's last few messages, their stated items, and per task: ID, title,
    media type, first 3 requirements. Listing text is data, not instructions.
  - Returns every ID best-first with a reason ≤140 characters.
  - Server drops unknown/duplicate IDs, appends skipped tasks in default order, never drops a task.
  - The reason replaces `explanation`; tasks without one keep a plain fallback line.
  - Never reserves or approves payment.
  - Own 15 s timeout (`GeminiFrames.structured_text` gains an optional `timeout`; existing callers
    keep 45 s).
  - Fixture mode, Gemini failure, timeout or invalid JSON → default order, `ranked: false`,
    warning logged.

## Task 2: chat flow and copy

Acceptance:

- Contributor intake asks only for items. Question: "What do you have on hand? Name any items,
  props, pets or places, or say 'nothing' and I'll show everything that's open."
- The question counts as answered when items were found (Gemini or the "I have…" parser), the
  contributor said nothing/no equipment, or they replied to the question at all.
- "Find work" → question. "I have a cup and no time limit" → ranked list immediately. Later
  "I also have a mug" → re-ranked list.
- Reply: "Here are N open tasks, best match first. Pick one to review its reward." Empty market:
  "There's no open funded work right now. Check back soon."
- If Gemini intake extraction fails for a contributor, fall back to the "I have…" parser instead
  of a 503. Buyer intake is unchanged.
- `work-chat.tsx`: header "Tell me what you have on hand. I'll show every open task, best match
  first."; starters "I have a cup and a kitchen table." / "I have a phone and a cat." /
  "Show me what's open."; "Matching on: cup, kitchen table. Tell me if this changes." (no time,
  underscores shown as spaces); fixture note "Fixture conversation · Tasks in default order, no AI
  ranking."; a small note when `ranked` is false outside fixture mode.

## Task 3: tests

Each new test fails on the old code first. Gemini is a fake adapter.

1. Buyer "a person pouring water into a cup" + contributor "I have a cup and no time limit" → the
   task is listed.
2. A contributor who never mentions a phone sees tasks.
3. "Find work" → question; answer "a cup" → list.
4. `rank_tasks` reorders, drops invented/duplicate IDs, appends skipped tasks, attaches reasons.
5. Gemini error/timeout → default order, `ranked: false`.
6. Contributor intake extraction failure → parser fallback, list still shown.
7. `create_batch` adds no `phone`; towel posts still get `towel`.
8. Empty market → "Check back soon" reply.
9. Existing `agents.py` / `search_tasks` tests pass unchanged.

E2E (`apps/web/e2e/collection.spec.ts`): the cat flow shows the list right after "I have a cat…"
with "Matching on: cat"; the time step is removed. New e2e: cup post + "I have a cup" contributor
sees it.

Real Gemini check: a one-off local script (not committed) runs `rank_tasks` with the real key on
the cup example plus two unrelated tasks; the cup task ranks first with a sensible reason.

Before asking to merge: full backend suite, web typecheck, unit tests, build, Playwright.

## Task 4: hosted switch to Arc testnet (settings only, done by the account owner)

Merge and confirm the code in fixture mode on the hosted app first. Then:

Railway:

| Setting | Value |
| --- | --- |
| `APP_MODE` | `testnet` |
| `ARC_CHAIN_ID` | `5042002` |
| `ALLOW_CHAIN_TRANSACTIONS` | `true` |
| `RUN_CHAIN_WORKER` | `true` |
| `ARC_RPC_URL` | `https://rpc.testnet.arc.io` |
| `ARC_ESCROW_ADDRESS` | `0xe613799458201e41830a5be3da5c2a7d18140da0` (current V3) |
| `ARC_ALLOCATOR_ADDRESS` / `ARC_ALLOCATOR_PRIVATE_KEY` | Operator wallet with test USDC for gas (owner enters) |
| `ALLOW_MODEL_TEXT` | `true` |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Owner's key / `gemini-3.5-flash-lite` |
| `ALLOW_MODEL_MEDIA` | `true` (required for testnet verification and payout) |

Vercel: `NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true`, `NEXT_PUBLIC_ARC_ESCROW_ADDRESS` = same escrow,
`NEXT_PUBLIC_ARC_CHAIN_ID=5042002`, then redeploy (build-time values).

Notes:

- `ALLOW_MODEL_MEDIA=true` sends sampled frames of contributor uploads to Gemini. On the free tier
  Google may use that data. Per-upload contributor consent is still required by the code.
- Fixture posts disappear in testnet mode. Buyers republish with test USDC (budget + gas);
  contributors need a little gas to confirm their content hash.
- Rollback: `APP_MODE=fixture` and restart. Matching still lists every task (unranked).
- Smoke test after switching: one buyer → contributor pass with the cup example.
