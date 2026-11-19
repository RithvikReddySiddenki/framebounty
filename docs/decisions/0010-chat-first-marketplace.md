# Chat-first intake and guided publishing

Buyers and contributors should describe their intent rather than learn equipment
labels or fill multiple forms. We add owned chat sessions reusing AgentSession
and AgentTurn, alongside the existing explicitly scoped agent tools. No migration
or escrow ABI change is needed. The old APIs remain compatible.

The model extracts only stated facts with exact user-quote evidence. The server
checks count, currency and time evidence separately so a 20-USDC budget cannot
silently become a count of 20 items. Missing subject, media type, count or budget
causes a buyer clarification. Missing equipment or time causes a contributor
clarification. Previously supplied facts survive short follow-up answers. Model
text is explicitly enabled; fixture parsing is labeled and deterministic.

Complete buyer facts produce a validated proposed plan whose type, count and
atomic budget must match those facts. Chat alone cannot create jobs, publish,
reserve work or approve payment. Contributor facts drive actual funded database
search. Optional AI ranking can select only IDs from those records. Task-specific
reservation still requires a visible user click and a fresh version/reward check.
An idempotency key preserves retries of that explicit reservation.

Chat messages and results are durable and wallet/role owned. Request IDs replay
the saved result and conflict if reused with different text. Model calls run
outside row locks. A locked revision check prevents competing messages from
overwriting each other's facts. Contributor chat restores the latest owned work
conversation; it clearly shows the equipment/time used and accepts corrections.
Old messages may display stale listings, so eligibility is rechecked at reservation.

Publishing is one explicit post/budget approval followed by a coordinator that
advances server-provided creation, exact allowance and deposit instructions. It
never manufactures calldata or signs with user keys. Each MetaMask authorization
is still required. Receipt polling automatically advances to the next step.
Existing hashes are saved before API calls and reconciled before another send.
Rejection, reverted receipts, timeout and navigation stop subsequent wallet prompts.
A hash returned after navigation is retained for recovery. Fixture publication is
one explicitly labeled simulated action. Draft saving remains optional.

Evidence: PostgreSQL chat tests cover missing fields, grounded numbers, real task
search, role/owner isolation, replay and concurrent updates. The exact publishing
coordinator is tested with external wallet/RPC boundaries for all three steps,
lost responses, decline, navigation, timeout and revert. Browser gates cover both
image/video flows and the testnet draft panels. Live AI connections and real Arc
wallet flows remain separate from deterministic test evidence.

Unlimited time is an explicit no_time_limit flag, not a made-up minute count.
Search omits only the duration predicate; funding, equipment, slots and deadlines
remain mandatory. Stated resources include pets and subjects, and direct possession
statements supplement semantic extraction when a resource was dropped. Corrections
are replayed in order so removed resources do not reappear. Existing conversations
can recover the stated preference from their saved messages on the next request.
