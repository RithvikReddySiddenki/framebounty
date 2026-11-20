# Vercel frontend, Railway processes, private Supabase data

The user authorized configuration only, with existing Vercel/Supabase accounts
and no Railway account. No hosted resources, subscriptions or deployments are
authorized by this slice. Integrate teammate camera work from main and deployment
container from feat/deploy before preparing hosting.

Keep the Next.js frontend on Vercel and send media directly to the Railway API.
This avoids routing bounded 100-MiB video bodies through frontend functions.
Use Supabase session-pooled PostgreSQL with TLS and a dedicated private
framebounty schema, not Supabase's exposed public schema. Circle remains the
identity provider; Supabase Auth and its public table API are not app interfaces.

Supabase Storage is the durable source for originals and decoded samples. The
API stages and validates uploads on local disk, persists objects, then commits
the submission reference. The worker restores originals and persists frames
before completing verification. Infrastructure failures retry without rejecting
or approving quality. A crash can leave a private unreferenced object; deletion
requires reference reconciliation and is not performed automatically.

The API checks authentication, ownership and payment before serving private
originals or watermarked previews. No public or signed object URLs bypass those
checks. Reject a public bucket even when a local cached copy exists. Backend
service-role credentials are never included in the frontend.

Use one Railway replica supervising API, verification worker and explicitly
enabled chain worker. Supabase media no longer requires shared local media, but
the operator's cumulative mainnet gas ledger still requires a persistent /data
volume and a single signer instance. API/worker failure stops the container.
Replicas or separate chain services need a shared atomic budget ledger first.

Preserve camera migration 0008 already on main; move the unpublished/unapplied
Circle migration to 0009. Do not stamp a database that applied the earlier branch's
Circle-only 0008: its schema differs and requires a reviewed reconciliation.

Validation: actual PostgreSQL migrations, file/object-boundary tests, remote-cache
restore through upload/verification/payment/export, local EVM, Chromium and build.
The hosted storage HTTP boundary is simulated. Live provider connectivity and a
Docker image build require available infrastructure and are reported separately.
