# Circle Google login and real-USDC setup

Target: Arc mainnet (chain 5042), Circle User-Controlled Wallets with Google login (email OTP optional),
and optional existing-wallet login. The current testnet environment remains
separate. Setup is not activation; do not copy testnet balances or escrow addresses
into mainnet. User authorized at most **1 real USDC total** for deployment and
the initial payment test, including network fees. No domain purchase or paid
subscription is authorized. Nothing has been spent.

## 1. Free Google-login setup (no custom sender domain)

1. Create your own account at https://console.circle.com/. Complete account access
   requirements without choosing a paid plan. If mainnet access requires a paid
   plan, stop and tell us; that is not part of the 1-USDC transaction allowance.
2. Create/select a Google Cloud project at https://console.cloud.google.com/.
   Open **Google Auth Platform**, configure the app name/support email and
   **External** audience. Use only basic identity scopes (openid, email, profile).
3. Create an OAuth client of type **Web application**. For the isolated local
   integration use `http://localhost:3003` as the authorized redirect URI.
   Add your own Google account under **Audience -> Test users** while testing.
   A public launch needs the appropriate Google publishing/access configuration
   and an HTTPS app URL (a hosted subdomain can work; SMTP is not required).
4. Copy the Google OAuth Client ID. No Google client secret belongs in browser code.
5. In Circle go to **Wallets -> User Controlled -> Configurator -> Authentication
   Methods -> Social Logins -> Google**. Enter the Google Client ID in **Client ID
   (Web)** and copy your Circle **App ID**.
6. Under **Keys -> Create a key -> API key -> Standard Key**, create the appropriate
   Developer API key. Distinguish testnet and mainnet credentials. Save it privately
   in this branch's ignored `.env`; never send it through chat.

The local integration variables are:

```text
CIRCLE_ENABLED=true
CIRCLE_LOGIN_METHOD=google
CIRCLE_APP_ID=<public Circle App ID>
CIRCLE_GOOGLE_CLIENT_ID=<public Google OAuth client ID>
CIRCLE_API_KEY=<private server-side Circle API key>
AUTH_ORIGIN=http://localhost:3003
NEXT_PUBLIC_API_URL=http://localhost:8003
```

The integration creates Circle EOA wallets, so existing signature/receipt checks
stay compatible. Users hold their keys through Circle's user-controlled product;
our backend never holds customer private keys. Google login and OTP both ultimately
produce a Circle-authenticated user session; the backend verifies wallet ownership.
Existing MetaMask login remains a separate option, not automatic email-account
linking. We do not merge two accounts solely because they claim the same email.

## 2. Optional email-code delivery (requires sender setup)

You need a sender domain that you or a teammate controls. Resend's free tier is
one option with SMTP support. At https://resend.com/, add your domain and install
the exact DNS records shown in its dashboard. Wait for verification. Do not buy
a new domain or paid plan as part of this setup without separate authorization.

In Circle's Email settings configure:

| Setting | Value |
| --- | --- |
| From | A sender on your verified domain, e.g. FrameBounty <login@your-domain> |
| SMTP host | smtp.resend.com |
| Port | 465 (TLS) |
| Username | resend |
| Password | Your Resend API key, entered privately in Circle Console |

Circle sends/validates the login code; Resend delivers it. Test using your own
inbox. Mailtrap Email Sandbox is suitable for development, but its sandbox inbox
is not production delivery to your users. Do not label it production-ready.

## 3. Local configuration and launch prerequisites

Use the isolated branch's own ignored `.env` file. Do not overwrite the existing
demo `.env`, database or testnet deployment. Production needs its own database,
private media root, HTTPS origin and dedicated mainnet operator wallet. Configure
credentials using the variables above. For email codes use CIRCLE_LOGIN_METHOD=email.
Never send recovery phrases, private keys, API keys or SMTP passwords in chat.

Before any real transaction, verify chain ID, canonical USDC, runtime bytecode,
exact recipient and amount, and a bounded maximum fee against the remaining
1-USDC allowance. The existing testnet operator has no implied mainnet funding.
Mainnet deployment is a new deployment; existing jobs remain on their old chain.

Sources checked 2026-11-20:
- https://developers.circle.com/wallets/user-controlled/build-a-wallet-app
- https://developers.circle.com/wallets/supported-blockchains
- https://resend.com/docs/send-with-smtp
- https://resend.com/pricing
- https://docs.arc.io/arc/references/connect-to-arc
- https://docs.arc.io/arc/references/contract-addresses


## 4. Mainnet activation is separate from authentication setup

For real USDC set `APP_MODE=mainnet`, `ARC_CHAIN_ID=5042`,
`NEXT_PUBLIC_ARC_CHAIN_ID=5042`, `ALLOW_MAINNET_TRANSACTIONS=true`, the verified
mainnet RPC `https://rpc.mainnet.arc.io`, canonical USDC
`0x3600000000000000000000000000000000000000`, and a new mainnet-compatible escrow.
Use a separate database/private storage and a dedicated funded operator key.
Keep `ALLOW_CHAIN_TRANSACTIONS=false` during deployment. The explicit CLI selection
is `scripts/deploy_arc.py --network mainnet`; the default is still testnet.
Only enable chain workers after the receipt/runtime and funded setup are verified.

The operator's cumulative gas cap is persisted in ignored `.local/mainnet-budget.json`.
Unknown transactions retain their full maximum; verified receipts release unused
headroom. Do not delete/reset this ledger. The initial user's 1-USDC allowance also
has to cover the initial buyer/contributor test's fees and reward, so do not spend
all of it on operator gas and then add an unbudgeted reward. Customer-approved
payments in a public marketplace are separate from this operator trial allowance.
No real deployment or transfer has been performed by this branch yet.
