# Workboard

Owner: implementation lead (Codex), branch `feat/framebounty-prototype`.
No concurrent editors have been identified. Shared interfaces are owned here until reassigned.

| Slice | Acceptance | Status |
| --- | --- | --- |
| Foundation | Reproducible shells, CI, plan/money rules and tests, state machine | c1e4406 pushed; remote CI unverified (connector transport failure) |
| Persistence/auth | PostgreSQL migrations, signed nonce, ownership enforcement | Implemented; 62 backend tests including real PostgreSQL passed, web build passed; preparing commit |
| Escrow | Contract accounting/security suite and local integration | Planned |
| Collection | Funded search, confirmed atomic reservation, private mobile upload | Database fixture search/confirmation/reservation implemented; real chain and upload pending |
| Review/payment | Bounded verification, reviewer decisions, durable reconciliation | Planned |
| Agents/export | Grounded tools, overlap-aware replanning, authorized dataset export | Planned |
| Live demo | Arc smoke, Gemini evaluation, real phone verification | Blocked on external setup |

Canonical interfaces: `services/api/framebounty/domain.py` owns plan and atomic money rules;
`docs/state-machine.md` owns intended escrow transitions. Changes must update consumers/tests together.
No implementation or deployment is claimed by a Planned row.

Interface update: task/confirmation/reservation/ledger HTTP atomic amounts serialize
as decimal integer strings so browser JavaScript cannot lose integer precision.
Draft plan validation currently accepts strict integer atomic amounts. Plan version/hash
is immutable for each saved draft. PostgreSQL migration 0001 owns the initial schema.
Fixture reservation state names are separated from live states by the `fixture_` prefix.
Live reservation attempts return 503 until chain-backed commitments exist.

Environment: isolated workspace PostgreSQL 18 cluster available on 127.0.0.1:55432;
Compose documents portable PostgreSQL 16. FFmpeg/ffprobe and Foundry absent. No
production credentials or real videos have been provided. User explicitly approved
feature-branch pushes to the configured GitHub repository on 2026-11-16.
