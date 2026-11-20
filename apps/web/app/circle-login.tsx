"use client";
import { useEffect, useRef, useState } from "react";
import type { W3SSdk } from "@circle-fin/w3s-pw-web-sdk";
import { SocialLoginProvider } from "@circle-fin/w3s-pw-web-sdk/dist/src/types";
import { configureArcNetwork, request, setEmbeddedWalletSender, setEmbeddedDraftRemover, type WalletTransaction } from "./api";

type Configuration = { chain_id: number; network: string; real_money: boolean; circle_enabled: boolean;
  circle_app_id: string; circle_login_method: "email" | "google"; google_client_id: string };
type LoginResult = { userToken: string; encryptionKey: string };
type Session = { wallet: string; token: string; expiresAt: number; method?: "circle" | "wallet" };
type Wallet = { id: string; address: string };
const pendingKey = "framebounty:circle:pending-login";

function execute(sdk: W3SSdk, id: string) {
  return new Promise<void>((resolve, reject) => sdk.execute(id, error => error ? reject(new Error("Circle authorization was not completed.")) : resolve()));
}

/** Device credentials survive only the Google redirect in this tab, for ten
 * minutes. Authenticated user tokens/keys stay in memory, never localStorage. */
export default function CircleLogin({ authenticated }: { authenticated: (session: Session) => void }) {
  const [config, setConfig] = useState<Configuration>();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [readyToVerify, setReadyToVerify] = useState(false);
  const [message, setMessage] = useState("");
  const sdkRef = useRef<W3SSdk | undefined>(undefined);
  const active = useRef(true);
  const completing = useRef(false);
  const initializeId = useRef("");

  useEffect(() => {
    let cancelled = false;
    active.current = true;
    request<Configuration>("/auth/config").then(async next => {
      if (!active.current || cancelled) return;
      configureArcNetwork(next.chain_id); setConfig(next);
      if (!next.circle_enabled) return;
      const { W3SSdk } = await import("@circle-fin/w3s-pw-web-sdk");
      let pending;
      try { pending = JSON.parse(sessionStorage.getItem(pendingKey) || "null"); } catch { sessionStorage.removeItem(pendingKey); }
      if (pending && (pending.expiresAt < Date.now() || pending.appId !== next.circle_app_id)) {
        sessionStorage.removeItem(pendingKey); pending = undefined;
      }
      if (pending?.initializeId) initializeId.current = pending.initializeId;
      if (!active.current || cancelled) return;
      if (pending) { setBusy(true); setMessage("Completing Circle sign-in…"); }
      const sdk = new W3SSdk({ appSettings: { appId: next.circle_app_id },
        ...(pending ? { loginConfigs: { deviceToken: pending.deviceToken, deviceEncryptionKey: pending.deviceEncryptionKey,
          google: { clientId: next.google_client_id, redirectUri: window.location.origin, selectAccountPrompt: true } } } : {}) },
        (error, result) => {
          if (!active.current || cancelled) return;
          if (error || !result) {
            const code = String(error?.code || "");
            const safeCode = /^[a-zA-Z0-9_-]{1,40}$/.test(code) ? ` (${code})` : "";
            setBusy(false); setMessage(`Google sign-in did not complete${safeCode}. Please try again.`); return;
          }
          void finish(result, sdk);
        });
      sdkRef.current = sdk;
      setReady(true);
    }).catch(() => { if (active.current) setMessage("Google sign-in is temporarily unavailable. Please try again shortly."); });
    return () => { cancelled = true; active.current = false; };
  }, []);

  async function finish(result: LoginResult, sdk: W3SSdk) {
    if (completing.current) return;
    completing.current = true; setBusy(true); setMessage("Opening your account…");
    try {
      sdk.setAuthentication(result);
      const body = { user_token: result.userToken };
      let wallets = (await request<{ wallets: Wallet[] }>("/auth/circle/wallets", undefined, body)).wallets;
      if (!wallets.length) {
        const initialization = await request<{ challenge_id?: string; wallets?: Wallet[] }>("/auth/circle/initialize", undefined,
          { ...body, request_id: initializeId.current || (initializeId.current = crypto.randomUUID()) });
        if (initialization.challenge_id) await execute(sdk, initialization.challenge_id);
        wallets = initialization.wallets || (await request<{ wallets: Wallet[] }>("/auth/circle/wallets", undefined, body)).wallets;
      }
      if (!wallets[0]) throw new Error("Your Circle account is still being created. Please sign in again shortly.");
      const wallet = wallets[0];
      const session = await request<{ wallet: string; token: string; expires_in_seconds: number }>("/auth/circle/login", undefined,
        { ...body, wallet_id: wallet.id });
      if (!active.current) { await request("/auth/logout", session.token, {}); return; }
      setEmbeddedWalletSender(async (transaction: WalletTransaction, intent_id?: string) => {
        if (!intent_id) throw new Error("An authorized marketplace intention is required.");
        if (transaction.from.toLowerCase() !== wallet.address.toLowerCase()) throw new Error("Reconnect the Circle account that owns this action.");
        const prepared = await request<{ intent_id: string; challenge_id?: string; tx_hash?: string }>("/circle/transactions", session.token, { ...body, transaction, intent_id });
        if (prepared.tx_hash) return prepared.tx_hash;
        const statusPath = `/circle/transactions/${prepared.intent_id}/status`;
        let status = await request<{ state: string; challenge_status: string; tx_hash?: string }>(statusPath, session.token, body);
        if (status.tx_hash) return status.tx_hash;
        if (status.state === "failed") throw new Error("This Circle authorization expired or failed. No payment is assumed.");
        if (status.challenge_status === "PENDING" && prepared.challenge_id) await execute(sdk, prepared.challenge_id);
        for (let attempt = 0; attempt < 60; attempt++) {
          status = await request(statusPath, session.token, body);
          if (status.tx_hash) return status.tx_hash;
          if (status.state === "failed") throw new Error("Circle transaction failed. No payment is assumed.");
          await new Promise(resolve => window.setTimeout(resolve, 2000));
        }
        throw new Error("Circle transaction is still pending. Retry this same action to reconcile its existing authorization.");
      });
      sessionStorage.removeItem(pendingKey);
      // Keep the Circle user token only in this in-memory closure, just like
      // transaction signing. Removal may inspect a failed/expired approval.
      setEmbeddedDraftRemover(jobId => request(`/jobs/${jobId}/remove`, session.token, body));
      window.history.replaceState(null, "", window.location.pathname);
      authenticated({ wallet: session.wallet, token: session.token, expiresAt: Date.now() + session.expires_in_seconds * 1000, method: "circle" });
    } catch (error) { if (active.current) setMessage(error instanceof Error ? error.message : "Circle sign-in could not be verified."); }
    finally { completing.current = false; if (active.current) setBusy(false); }
  }

  async function begin() {
    const sdk = sdkRef.current;
    if (!sdk || !config || busy) return;
    setBusy(true); setMessage("");
    try {
      initializeId.current = crypto.randomUUID();
      const device = await request<{ deviceToken: string; deviceEncryptionKey: string; otpToken?: string }>("/auth/circle/otp", undefined,
        { device_id: await sdk.getDeviceId(), ...(config.circle_login_method === "email" ? { email } : {}) });
      if (config.circle_login_method === "google") {
        sessionStorage.setItem(pendingKey, JSON.stringify({ ...device, initializeId: initializeId.current, appId: config.circle_app_id, expiresAt: Date.now() + 600000 }));
        sdk.updateConfigs({ appSettings: { appId: config.circle_app_id }, loginConfigs: { ...device,
          google: { clientId: config.google_client_id, redirectUri: window.location.origin, selectAccountPrompt: true } } });
        await sdk.performLogin(SocialLoginProvider.GOOGLE);
      } else {
        sdk.updateConfigs({ appSettings: { appId: config.circle_app_id }, loginConfigs: device });
        setReadyToVerify(true); setMessage("Code sent. Continue to enter it securely with Circle."); setBusy(false);
      }
    } catch (error) { setBusy(false); setMessage(error instanceof Error ? error.message : "Circle sign-in is unavailable."); }
  }
  return <div className="circle-signin">
    {config?.circle_enabled ? <>
      {config.circle_login_method === "email" && <label>Email address<input type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} disabled={busy} /></label>}
      <button className="primary signin-button" disabled={!ready || busy || (config.circle_login_method === "email" && !email)}
        onClick={() => readyToVerify ? sdkRef.current?.verifyOtp() : void begin()}>
        {busy ? "Signing in with Circle…" : readyToVerify ? "Enter email code" : config.circle_login_method === "google" ? "Continue with Google" : "Continue with email"}
      </button><p className="signature-note">Powered by Circle. No wallet extension required.</p>
    </> : <p className="signature-note">Google sign-in is being configured. Please try again shortly.</p>}
    {message && <p role="status">{message}</p>}
  </div>;
}
