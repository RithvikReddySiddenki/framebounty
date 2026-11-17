# 0004: Two logical agents with closed server tools

Context: conversation text can invent listings, request privileged actions or mix buyer
and contributor identity. A reservation tool may commit before an agent response is saved.

Options: a general orchestration framework with prompt-only permissions, or two owned
logical roles using ordinary domain services. Choice: the latter, sharing the Gemini
adapter while keeping wallet, role, optional buyer job scope, contributor profile and
turn history in distinct persistent records. The confirmed contributor profile is
immutable per conversation; changing equipment/time requires a new conversation.

Buyer tools propose draft plans, inspect their scoped owned job, and commission a
validated next batch under existing policy. Contributor tools search real eligible
records, read terms, prepare a confirmation, reserve an explicitly confirmed task,
and inspect only their wallet's work. Neither role has a quality-approval or arbitrary
transfer tool. Initial simulated funding still requires the ordinary UI's confirmation.

The model receives only the current role/session's bounded history. Closed proposal
schemas permit only role-appropriate actions; all arguments are revalidated server-side.
Contributor chat can select search or work tracking, never reservation. The separate
confirmation control sends the displayed task/version/reward to the contributor tool.

Turn intents precede tool execution. Stable turn IDs key reservation/batch idempotency
and confirmation creation. On a restart, a prepared intent resumes through the same
domain service rather than repeating payment or inventing success. Completed results
are cached; reusing a request ID for different input fails. A late failed model request
cannot overwrite an already prepared/completed decision. Denied role tools are audited.

Fixture planning is explicitly a fixed towel example; fixture recommendations query
actual database listings. Live Gemini text requires explicit ALLOW_MODEL_TEXT consent
and configured account/model access, fails visibly on invalid output/outage, and never
falls back to fixtures. No live-provider recommendation-accuracy claim is made.

Validation: real PostgreSQL role/session isolation, profile eligibility, prompt/tool
injection, invented IDs, HTTP authorization, simultaneous/restarted reservation retries,
provider failures, and context isolation. Chromium now drives planning, search, explicit
reservation, upload/review, and next-batch commissioning through both logical agents.
