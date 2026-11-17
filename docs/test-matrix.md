# Test matrix

Actual persistence/auth run, 2026-11-16:
`$env:TEST_DATABASE_URL='postgresql+psycopg://framebounty@127.0.0.1:55432/framebounty'`
then `./.venv/Scripts/python.exe -m pytest services/api/tests -q -p no:cacheprovider --basetemp=.local/pytest-auth-01`:
**62 passed**, including six real PostgreSQL tests with migration upgrade/downgrade.
One upstream Starlette warning about the httpx test client; no skipped tests.
An earlier full run had 56 passes and six temp-fixture setup errors due to Windows
profile temp-directory permissions; fresh workspace-local temp storage resolved them.
An earlier malformed-media regression failed once and was fixed, not removed.
`npm run typecheck` and `npm run build` in apps/web: **passed**.
`npm install`: 0 reported dependency vulnerabilities at install time.

| IDs | Requirement / file | Evidence |
| --- | --- | --- |
| B01 (partial), C07 (off-chain only) | Exact money and closed plan schema; tests/test_domain.py | Passed |
| B02 (pure rules only), I12 (not integration) | Overlap and committed targets; tests/test_domain.py | Passed unit coverage only |
| HTTP shell | tests/test_http.py | Passed; invalid draft returns 422, health disables payments |
| B05 (EOA only), I07 (job reads only) | tests/test_auth.py, tests/test_postgres.py | Passed nonce/wallet binding, replay/expiry, concurrent login, cross-wallet job access |
| B09, B11, I02 (DB fixture only), I09/I10 (partial) | tests/test_postgres.py | Passed actual database search, equipment/time filters, confirmation, idempotency, race/budget protection |
| B04 (adapter only), B10 (assessment schema only), B13 (observation boundary only) | tests/test_verification.py | Passed malformed/timeout/429/500/incomplete provider responses; no live model calls |
| B06/B12 (helpers only) | tests/test_media.py | Passed path/header/hash/metadata limits and malformed-input regression; no real decoding run |
| C01–C09 | Solidity security/accounting | Not implemented; Foundry absent |
| B03–B14 remaining portions | Upload, durable processing, complete role tools, review/payment behavior | Not implemented |
| I01–I12 remaining portions | Chain-backed collection/review/payment/reconciliation/export | Not implemented; no local-chain integration evidence |
| E01–E06 | Browser workflow | Not implemented; build is not browser evidence |
| Model evaluation | Labeled held-out samples, recommendation evaluation | Not run; no consented videos or provider credentials |
| Arc smoke | Deploy/fund/reserve/submit/pay/reconcile/refund | Not run; no funded wallets or deployment |

Git: foundation c1e4406 pushed to the feature branch. GitHub connector transport
failed while fetching remote CI; local success is not a remote-CI claim.

The planned IDs are taken from PROJECT_BRIEF.md. Partial coverage never marks an
entire requirement complete. No local or mocked result proves Arc or Gemini behavior.
