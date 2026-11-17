# 0001: Small services and explicit trust

Context: deliver one understandable video marketplace workflow without conflating AI
judgment with quality approval or local fixtures with blockchain evidence.

Options: orchestration framework/Redis, or narrow adapters and PostgreSQL durable jobs.
Choice: the latter, with independent buyer/contributor logical roles and human review.
Rationale: fewer operational dependencies; authorization and accounting remain ordinary code.
Risks: database job leasing and transaction reconciliation still require concurrency tests;
reviewer abandonment is a disclosed trust limitation, not automatic acceptance.
Validation: domain unit tests now; real PostgreSQL/local-chain and browser gates before completion.
