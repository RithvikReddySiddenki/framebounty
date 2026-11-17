# Workboard

Owner: implementation lead (Codex), branch `feat/framebounty-prototype`.
No concurrent editors have been identified. Shared interfaces are owned here until reassigned.

| Slice | Acceptance | Status |
| --- | --- | --- |
| Foundation | Reproducible shells, CI, plan/money rules and tests, state machine | In progress |
| Persistence/auth | PostgreSQL migrations, signed nonce, ownership enforcement | Planned |
| Escrow | Contract accounting/security suite and local integration | Planned |
| Collection | Funded search, confirmed atomic reservation, private mobile upload | Planned |
| Review/payment | Bounded verification, reviewer decisions, durable reconciliation | Planned |
| Agents/export | Grounded tools, overlap-aware replanning, authorized dataset export | Planned |
| Live demo | Arc smoke, Gemini evaluation, real phone verification | Blocked on external setup |

Canonical interfaces: `services/api/framebounty/domain.py` owns plan and atomic money rules;
`docs/state-machine.md` owns intended escrow transitions. Changes must update consumers/tests together.
No implementation or deployment is claimed by a Planned row.
