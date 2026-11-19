# 0008: Sign-in before every product service

Context: the user requires authenticated access to every marketplace service and
a role-oriented frontend. Task search and plan validation were public, and the
old page rendered workspace controls before sign-in. Client-only hiding is not
sufficient authorization.

Choice: a FastAPI application-wide dependency denies product routes by default.
Only exact POST /auth/challenge, POST /auth/login and minimal GET /health are
public. Swagger, ReDoc and the schema route are disabled. Existing single-use,
origin/chain-bound EOA challenges and hashed opaque sessions remain. Ownership
and immutable agent-role restrictions stay independent of authentication. Logout
revokes the current server token without invalidating other signed-in devices.

The client mounts no marketplace/agent/review component before the real signed
login completes. Account/network/provider changes, expiry and a matching token's
HTTP 401 clear the workspace. Token-bound expiry events and an attempt counter
prevent late requests or sign-in/wallet-switch races from replacing a newer
session. Tokens remain in memory; reload requires sign-in again.

Design sources supplied by the user:
- Prolific: clear rewards, time, requirements and submission status.
  https://www.prolific.com/participants
- Upwork/Uma: AI help integrated into buyer/contributor workflows. The main URL
  returned 403; official product/help results supplied the pattern.
  https://www.upwork.com/uma/
  https://support.upwork.com/hc/en-us/articles/22983791592595-How-to-use-Uma-Upwork-s-Mindful-AI-as-a-freelancer
- Linear: quiet sidebar, location/view hierarchy and softer visual structure.
  https://linear.app/now/behind-the-latest-design-refresh

Implementation: compact navigation, genuine database overview counts, separate
planning/review views, fixed-reward/time task cards, a dedicated submissions view
and contextual agent help. No listings or earnings are invented. No external
fonts are fetched on the sign-in screen. Review/submission refreshes update the
actual status and overview counts rather than leaving stale labels.

Alternatives: client-only gating and per-handler opt-in authentication. Rejected
because a forgotten endpoint could expose services. Sign-in bootstrap and minimal
liveness are required public exceptions that expose no marketplace records.

Limits: wallet ownership is not identity verification. ERC-1271, device/session
management and auth rate limits remain future work. Visual role switching grants
no new ownership/reviewer permissions. Arc financial logic is unchanged.

Validation: anonymous route enumeration; real PostgreSQL signed access, logout,
expiry and ownership; six Chromium cases for the sign-in gate, signature refusal,
logout, expiry, wallet changes/reload and the full synthetic collection workflow.
Desktop sign-in/dashboard and mobile submissions screenshots were inspected.
One initial error selector also matched Next's route announcer; an accessible
error name fixed the selector without weakening the signature-refusal assertion.
