# Test matrix

Actual foundation run, 2026-11-16:
`./.venv/Scripts/python.exe -m pytest services/api/tests -q`: **20 passed**.
One upstream Starlette warning about the httpx test client; no skipped tests.
`npm run typecheck` and `npm run build` in apps/web: **passed**.
`npm install`: 0 reported dependency vulnerabilities at install time.

| IDs | Requirement / file | Evidence |
| --- | --- | --- |
| B01 (partial), C07 (off-chain only) | Exact money and closed plan schema; tests/test_domain.py | Passed |
| B02 (pure rules only), I12 (not integration) | Overlap and committed targets; tests/test_domain.py | Passed unit coverage only |
| HTTP shell | tests/test_http.py | Passed; invalid draft returns 422, health disables payments |
| C01–C09 | Solidity security/accounting | Not implemented; Foundry absent |
| B03–B14 | Auth, media, provider, reservation, review | Not implemented |
| I01–I12 | Real PostgreSQL + local chain | Not run; Docker engine unavailable |
| E01–E06 | Browser workflow | Not implemented; build is not browser evidence |
| Model evaluation | Labeled held-out samples, recommendation evaluation | Not run; no consented videos or provider credentials |
| Arc smoke | Deploy/fund/reserve/submit/pay/reconcile/refund | Not run; no funded wallets or deployment |

The planned IDs are taken from PROJECT_BRIEF.md. Partial coverage never marks an
entire requirement complete. No local or mocked result proves Arc or Gemini behavior.
