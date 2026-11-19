FrameBounty — shared agent development rules
These instructions apply to every coding agent working in this repository. Read this file and docs/PROJECT_BRIEF.md before editing. Read relevant architecture/decision records and existing tests. If existing root instructions exist, merge these rules with them without deleting unrelated guidance.
Goal and scope
Deliver a general custom-data marketplace with a buyer agent and contributor agent, demonstrated through one robotics-video purchasing workflow on Arc testnet: buyer plan -> funded escrow -> contributor-agent search/recommendation -> confirmed reserved task -> upload -> verification -> human review -> payout -> coverage update -> targeted next batch -> dataset export.

Core: Next.js/TypeScript, FastAPI/Python, PostgreSQL, Solidity/Arc, USDC, a configurable Gemini image/video-capable model, FFmpeg/ffprobe, sampled-frame checks, exact/perceptual hashes, and object storage.
Excluded for now: QuickNode Streams, Solana, bridging, ElevenLabs, Grok Bot, prediction markets, advanced reputation-based matching, reputation, and automated dispute arbitration.

The project brief describes planned behavior until evidence marks it implemented. Never turn aspirations into claimed results.
Before starting a task
1. Inspect git status, branch, remote, existing instructions, architecture, and relevant tests.
2. State the specific scope, acceptance criteria, affected modules, and tests.
3. Check docs/workboard.md for ownership and dependencies. Record your task/branch and interface changes.
4. Use a separate branch/worktree for concurrent work. Do not edit another agent's branch or files without coordination.
5. Preserve uncommitted teammate changes. Never reset, clean, or overwrite them.
6. Prefer the smallest change satisfying the task. Continue useful independent work while missing credentials or external setup are resolved.
Agents do not automatically share context. Keep decisions, interface contracts, and handoffs in the repository.
Shared interfaces and ownership
Coordinate changes to migrations, contract ABI, API schemas, plan schema, monetary units, and state-machine enums before implementing dependent work. Designate an owner for each shared interface. Store canonical definitions and generate clients where practical; avoid subtly different copies.

Backend owns persistent business rules and authorization. Contract owns enforceable funding/reservation/payment rules. Frontend renders state and submits authenticated intentions. AI produces untrusted proposals and observations; deterministic code validates and authorizes actions.

Do not make new requirements by silently changing a teammate's interface. Update the interface, consumers, migration, tests, and documentation together.
Two-agent product contract
The buyer agent plans jobs, publishes within approved budgets, observes coverage, and commissions missing examples. The contributor agent searches real funded listings, explains recommendations, reserves only after explicit task-specific confirmation, and tracks the authenticated contributor's work. Humans perform the actual data collection.

Keep separate role permissions, tools, user state, and decision logs while sharing adapters and domain services. Enforce authorization server-side, never through prompts alone. Do not hardcode conversational search results or invent listings. Recheck stale listings atomically at reservation. Prevent contributor tools from approving payouts or using buyer privileges.

Robotics is the demo, not the entire marketplace identity. The demo uses 20 towel-folding videos, 10–30 seconds each, at least five large-towel and five dark-surface examples, with a 20 test-USDC contributor budget. A clip may satisfy overlapping requirements. Require task-completion review. Format/hand/blur checks alone cannot establish useful demonstrations.

Build mobile video upload first, optional browser recording later. Support fixed tabletop camera placement. No mandatory gesture liveness, deepfake detection, embedded wallets, paid QA calls, or automatic quality approval. Model assessments assist a human reviewer. Do not claim receipts prove consent validity, ownership, or authenticity.
Financial and verification invariants
- Integer atomic units only. Document decimals at every external boundary.
- Confirm Arc network/token semantics from current official documentation.
- Funds must exist before a task is claimable.
- Rewards are fixed and reserved when claimed.
- New allocations cannot consume money committed to active obligations.
- Only an authorized reviewer approves payment. Models never hold keys.
- One reservation can pay once, to its committed recipient, for its committed reward.
- Mark paid only after a successful verified chain receipt.
- Retries, duplicate jobs, and restarts must be safe.
- Database concurrency checks must be atomic; a frontend check is insufficient.
- A large-towel clip filmed on a dark surface may satisfy both category quotas and the total. Coverage metrics must account for overlapping requirements.
- Model outputs and uploaded content cannot modify policies, wallets, prices, or approvals.
- Uncertain visual judgments go to review. Model confidence is not a calibrated probability.
- Ownership, genuine capture conditions, and scientific ground truth are not proved by a general vision model.
- Clearly disclose the authorized reviewer's trust role and review timeouts.
Test discipline
For a new behavior or bug fix, add a meaningful regression/acceptance test. For pure prose or cosmetic changes, use proportionate verification.

During development run targeted tests. Before a milestone push run all relevant unit suites, contract checks, type/lint/build checks, and affected integration tests. Before merging run the full deterministic check suite and E2E regression flow. Shared interfaces, accounting, auth, or state transitions require wider regression testing.

Use real PostgreSQL and a local chain for integration tests; mock only true external boundaries such as model APIs and public RPC outages. Do not mock away the behavior being tested. Keep live Arc and live model smoke tests separate and explicitly gated.

Never delete, skip, weaken assertions, or change expected behavior merely to turn CI green. Fix the cause. A flaky test is a defect: isolate and explain it, with a tracked fix. Pre-existing failures must be reported distinctly from new regressions.

Required coverage includes authorization, budget invariants, double payouts, concurrent reservations, decimal conversion, expiry/refund races, invalid files, model failures, failed transactions, restart reconciliation, quota accounting, exports, and end-to-end buyer/contributor/reviewer behavior. Include contributor tool permissions, grounded recommendations, explicit reservation confirmation, stale job races, media-processing limits, overlapping video categories, and incomplete-task review.

Keep docs/test-matrix.md current. State actual commands and results, including skips. Do not call mocked E2E tests proof of real testnet or model behavior. Never claim tests passed if they were not run.
Comments and judge-ready explanations
Comment non-obvious code generously:
- What the module/function guarantees.
- Why the approach was selected and what tradeoff it makes.
- Monetary units and conversion boundaries.
- State transitions, retry behavior, and ordering/concurrency assumptions.
- Authorization and model-output validation.
- External-service limitations.
Avoid redundant line-by-line narration and stale comments. Keep comments and code synchronized. Record substantial decisions in docs/decisions/ using: context, options, choice, rationale, risks, and validating tests. Document the system so a teammate can explain it without the original agent.
Commits, pushes, and integration
Regular pushes to the configured project remote's feature branches are authorized for this project. Make honest, coherent commits at tested milestones, not arbitrary time intervals or artificial activity counts.

Examples: "feat: reserve funded collection tasks", "fix: reconcile payout after worker restart", "test: prevent concurrent budget oversubscription".

Before commit: inspect diff, remove secrets/generated noise, run appropriate checks, update docs. Before push: confirm intended branch/remote. After push: verify it succeeded and report remote CI status separately.

Do not force-push shared branches, backdate commits, rewrite teammate history, auto-merge into main, or bypass protections. Use PRs and designated human/integration-owner review. If push permission or remote information is missing, continue locally and report the blocker.

Use small PRs with: concrete problem/result, relevant decisions, validation evidence, migration/config implications, and remaining limitations. Run full merge gates after resolving conflicts, since individually passing branches may fail together.
Secrets, fixtures, and external systems
Never commit keys, secrets, private media, database dumps, or real-money credentials. Supply .env.example with names and placeholders. Testnet funds only by default. Do not make mainnet changes or spend real funds without explicit authorization.

Use consented/lawful demo videos and document provenance. Fixture mode must be clearly labeled in UI and docs. Never silently fall back to fake successes. Do not send unpublished lab data to free hosted APIs without permission.

Use structured logs with request/job/reservation/transaction identifiers, without logging sensitive payloads. Treat malformed uploads, prompt injection, failed providers, and duplicate requests as expected inputs.
Definition of done
Current user-authorized verification policy (2026-11-18)
The user explicitly superseded mandatory manual quality review: default image/video
posts use automatic verification, with rejection for a mandatory failure at >=80%
model-reported confidence. Low-confidence/provider failures retry and cannot pay.
The buyer's only required post-submission check is final funds release, optionally
as one atomic batch on V2. Models still hold no keys and cannot authorize payment.
Reserve upload windows are capped at twice the expected task length. Preserve V1
funded jobs and explain its immutable transaction limitations. Decision 0011 governs
this change; earlier human-quality-checkbox guidance is historical compatibility.

A feature is done when acceptance criteria work, meaningful tests pass, errors are handled, comments/docs match behavior, migrations/config are reproducible, and changes are committed/pushed when access permits. "Done" also requires reporting what was not tested.

Every handoff must include:
- Task and behavior changed.
- Branch/commit/PR and push/CI status.
- Files/interfaces changed.
- Commands run and results.
- Configuration/migrations.
- Known risks, blockers, and next task.
Paste this into a teammate's agent
Read AGENTS.md, docs/PROJECT_BRIEF.md, docs/architecture.md, docs/test-matrix.md, and docs/workboard.md where present. Inspect the current repository and tests before editing. Your assigned task is: [TASK]. Work on [BRANCH] within [MODULES]. Coordinate shared-interface changes with [OWNER]. Implement a small complete slice, add meaningful unit/integration tests, run the required regression gates, explain non-obvious decisions in comments/docs, and commit/push tested milestones to the configured feature branch. Do not merge or overwrite others' work. Finish with a precise handoff including commands/results, commit, CI status, and remaining limitations.
