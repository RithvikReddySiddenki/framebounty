# FrameBounty demo runbook

This runbook starts the local FrameBounty stack for either a fully simulated
walkthrough or an explicitly enabled Arc testnet walkthrough. It does not deploy a
contract, fund a wallet, seed fixture data, or send a transaction by itself.

`scripts/demo.ps1` loads documented settings without displaying their values,
applies migrations, and starts the API, media worker, web app, and (in testnet
mode) chain worker. Process IDs and logs are stored in `.local/demo/`. The stop
action checks each recorded process start time before stopping its complete process
tree, so it does not stop an unrelated process that later reused the same PID. If
Windows refuses tree termination, the action fails and preserves `pids.json`
instead of killing only the parent and leaving an untracked child behind.

## Prerequisites

- Windows PowerShell 5.1 or newer.
- Python 3.12+ with the repository virtual environment and API dependencies:

  ```powershell
  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r services/api/requirements.lock
  .\.venv\Scripts\python.exe -m pip install --no-deps -e './services/api[test]'
  ```

- Node.js 22+ and the web dependencies:

  ```powershell
  npm ci --prefix apps/web
  ```

- FFmpeg and ffprobe. Install the repository-managed binaries with:

  ```powershell
  .\.venv\Scripts\python.exe scripts/setup_media_tools.py
  ```

  Absolute `FFMPEG_BIN` and `FFPROBE_BIN` settings are also supported.

- PostgreSQL. Either start the Compose service with `docker compose up -d
  postgres`, or point `DATABASE_URL` at any reachable PostgreSQL instance. SQLite
  is not supported. The launcher applies Alembic migrations through `head`.
- MetaMask or another browser wallet compatible with the MetaMask provider API.
  Wallet sign-in is required in both modes; signing the login challenge does not
  grant payment authority.

Copy `.env.example` to the ignored `.env` file and edit it locally. Do not put
keys in a `NEXT_PUBLIC_` setting, commit `.env`, or paste keys into logs or issue
reports. The API does not otherwise load `.env`; the launcher calls
`scripts/load-env.ps1` for its child processes.

## Fixture mode

Fixture mode is simulated and sends neither chain transactions nor media to
Gemini. The launcher forces `APP_MODE=fixture`, disables every live chain/model
flag, removes Gemini and allocator credentials plus live chain configuration from
the child-process environment, and uses a simulated passing verification result
so the complete local walkthrough can reach its clearly labeled simulated release
state. The calling terminal's original settings are restored after startup.

```powershell
.\scripts\demo.ps1 -Mode fixture -Action start
.\scripts\demo.ps1 -Action status
# Walk through the app at http://localhost:3000
.\scripts\demo.ps1 -Action stop
```

If `DATABASE_URL` is absent, fixture mode uses the Compose default at
`localhost:5432`. To create an additional clearly labeled fixture listing, run
the following after migrations, using a public demo wallet address:

```powershell
.\.venv\Scripts\python.exe -m framebounty.demo --buyer 0xYOUR_PUBLIC_DEMO_WALLET
```

Fixture rewards and releases are never redeemable and must not be presented as
testnet payment evidence.

## Testnet mode

Testnet mode can make real Arc testnet calls and send consented media samples to
Gemini. It refuses to start unless all required values and explicit gates below
are present. Put these settings in `.env`; replace only the placeholders. Keep the
allocator key local and use a dedicated allocator wallet, never a buyer or
contributor key.

```dotenv
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:PORT/DATABASE
APP_MODE=testnet
AUTH_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_URL=http://localhost:8000

GEMINI_API_KEY=<local-secret>
GEMINI_MODEL=gemini-3.5-flash-lite
ALLOW_MODEL_TEXT=true
ALLOW_MODEL_MEDIA=true

ARC_RPC_URL=https://rpc.testnet.arc.io
ARC_CHAIN_ID=5042002
ARC_ESCROW_ADDRESS=0xe613799458201e41830a5be3da5c2a7d18140da0
ARC_ALLOCATOR_ADDRESS=<dedicated-public-address>
ARC_ALLOCATOR_PRIVATE_KEY=<dedicated-local-secret>
ALLOW_CHAIN_TRANSACTIONS=true
NEXT_PUBLIC_ENABLE_CHAIN_FUNDING=true
```

`STORAGE_ROOT` may be left at `.local/media`. `ARC_USDC_ADDRESS` is not consumed
as a configurable token address: the backend pins Arc testnet's canonical USDC
ERC-20 interface in code. Its verified address is
`0x3600000000000000000000000000000000000000` with 6-decimal token amounts. Arc
uses the same USDC balance for native gas accounting with 18-decimal native units;
do not interchange those units.

For the default development server, start with:

```powershell
.\scripts\demo.ps1 -Mode testnet -Action start
```

For a production build, `NEXT_PUBLIC_*` values are fixed at build time. Load the
same `.env`, build, and then select `start` mode:

```powershell
.\scripts\load-env.ps1
npm --prefix apps/web run build
.\scripts\demo.ps1 -Mode testnet -Action start -WebMode start
```

The launcher checks PostgreSQL and FFmpeg, rejects occupied API/web ports, applies
migrations, and waits for HTTP 200 from the API health route and web page. Check
`.local/demo/*.err.log` when a process exits or readiness times out.

### Arc wallet checklist

Use three distinct test-only wallets:

1. **Buyer:** holds the collection budget plus gas and signs job creation, exact
   USDC approval, deposit, and optional early release.
2. **Contributor:** must differ from the buyer, holds enough gas, and signs the
   submitted content hash.
3. **Allocator/oracle:** the dedicated backend wallet configured above, funded for
   reservation, verification, rejection, expiry, and settlement transactions.

Arc testnet settings:

- Chain ID: `5042002` (`0x4cef52`)
- RPC: `https://rpc.testnet.arc.io`
- Explorer: `https://explorer.testnet.arc.io`
- Faucet: `https://faucet.circle.com`
- Native currency: USDC (18 native decimals)

The web app requests a switch to Arc testnet and offers to add it when the wallet
does not know the network. Fund all three wallets before rehearsal. Never share a
seed phrase or private key; only public wallet and transaction addresses belong in
the demo record.

## Phone or LAN upload

Use HTTPS for a real phone/wallet setup whenever possible; browser wallet and
media features can be restricted on insecure non-local origins. For a trusted
local-network rehearsal, find the laptop's LAN address, allow only the chosen API
and web ports through the local firewall, and set both public origins explicitly:

```dotenv
AUTH_ORIGIN=http://192.0.2.10:3000
NEXT_PUBLIC_API_URL=http://192.0.2.10:8000
```

Then start on all interfaces:

```powershell
.\scripts\demo.ps1 -Mode fixture -Action start -ListenHost 0.0.0.0
```

Replace the example address with the laptop's actual LAN address and open that web
origin on the phone. For testnet, rebuild the web app after changing
`NEXT_PUBLIC_API_URL` when using `-WebMode start`. Return the firewall and listen
address to their prior state after the rehearsal. Physical phone upload remains an
interactive check; a desktop viewport test is not evidence that it passed.

## Live walkthrough and evidence to save

The complete testnet flow has not yet been validated; treat the first run as a
careful smoke test and keep the fixture recording as a backup.

1. Run `-Action status` and confirm the API and web both report 200. Confirm the
   media and chain workers remain `running`.
2. Buyer signs in, asks the buyer agent for a small image or 10–30 second video
   collection, reviews the exact count/budget/rights, and publishes. Record the
   explorer links for `createProtectedJob`, USDC `approve`, and `deposit`.
3. A different contributor wallet asks the work agent for matching tasks, confirms
   the displayed fixed reward and deadline, and reserves. Record the allocator's
   `reserve` transaction.
4. The contributor uploads the correct media and signs `submit(contentHash)`.
   Record that transaction and the visible content-hash/status evidence.
5. Wait for per-criterion Gemini findings. Record the allocator's `verify` and
   evidence-hash transaction, or the rejection transaction and visible reasons.
6. For a successful rehearsal, the buyer may use early batch release rather than
   waiting one hour. Record the `approveBatch` transaction and the contributor's
   before/after public balance. If demonstrating automatic settlement later,
   record `settle` separately.
7. Confirm payment before showing the original/export, inspect coverage and the
   deterministic next batch, and optionally record both parties' rating
   transactions.

Save public transaction hashes and explorer URLs only. For the judge README, keep
deployment evidence distinct from a funded workflow: the existing V3 deployment
transaction alone does not prove reserve, verification, or payout.

## Troubleshooting

**Wrong chain.** MetaMask must show Arc testnet, chain `5042002`. Let the app switch
or add the network, then sign in again. A session is invalidated when the connected
account or chain changes.

**MetaMask nonce or unknown transaction state.** Do not click repeatedly or reset
the wallet nonce immediately. Inspect wallet activity and the Arc explorer first.
The app stores durable transaction intent and may recover an existing transaction
hash. A reverted intent is terminal; follow the UI's new-action path rather than
pretending the old hash succeeded.

**Gemini 429, quota, or provider failure.** Stop sending new requests and wait for
the provider window to reset or use a verified available model. Do not silently
switch to fixtures in a testnet run. Provider failures and low-confidence or
uncertain findings remain pending and cannot pay.

**Verification remains uncertain or pending.** Confirm the media worker is
`running`; inspect `media-worker.err.log`; verify `ALLOW_MODEL_MEDIA=true`, model
access, upload consent, and that FFmpeg can decode the file. Protected submissions
retry after provider failures and may legitimately stay held instead of passing.

**Reservation, attestation, or settlement remains pending.** Confirm the chain
worker is `running`; inspect `chain-worker.err.log`; verify the allocator address
matches its key, all three wallets have gas, and the RPC/escrow/chain values are
correct. A worker outage delays permissionless settlement but does not authorize a
fake paid state.

**Worker is not running.** Use `-Action status`, then read the corresponding logs
under `.local/demo/`. Stop the recorded stack and restart it after correcting the
configuration. Do not start duplicate workers against the same live database.

**Port already in use.** Stop the process you own or choose `-ApiPort` and
`-WebPort`, then update `AUTH_ORIGIN` and `NEXT_PUBLIC_API_URL` to match. The stop
action only targets processes recorded in `.local/demo/pids.json`.

**Process tree could not be stopped.** Windows refused the tree-termination
request, so the script deliberately returned an error and retained `pids.json`.
Do not delete the recovery file or assume child servers exited. Close the recorded
process tree with Task Manager or correct the local permission problem, then rerun
the stop and status actions.

## Shutdown

```powershell
.\scripts\demo.ps1 -Action status
.\scripts\demo.ps1 -Action stop
.\scripts\demo.ps1 -Action status
```

After shutdown, the recorded API, worker, and web processes should show stopped or
absent and both HTTP probes should be unreachable. Logs remain in `.local/demo/`
for diagnosis. The script does not stop PostgreSQL or delete databases, media,
wallet state, logs, or transaction records.
