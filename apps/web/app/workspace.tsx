"use client";
import { moneyUnit, networkName, explorerUrl } from "./api";

import { useEffect, useRef, useState } from "react";
import { authenticate, request, walletEventEndsSession, watchWalletChange, setEmbeddedWalletSender } from "./api";
import Contributor from "./contributor";
import CircleLogin from "./circle-login";
import Posts from "./posts";
import PostComposer from "./post-composer";
import { ExplorerLink, Icon, type IconName } from "./ui";

type Session = { wallet: string; token: string; expiresAt: number; method?: "circle" | "wallet" };
type Overview = {
  collections: number;
  open_collections: number;
  awaiting_review: number;
  fixture: boolean;
};
type View = "overview" | "collections";

/** Public escrow address, display-only (never a secret). Optional. */
const ESCROW = process.env.NEXT_PUBLIC_ARC_ESCROW_ADDRESS || "";

/** The end-to-end flow, shown on the landing page and the buyer overview so a
 * first-time viewer understands who does what before touching anything. */
const PIPELINE: { who: string; cls: string; icon: IconName; title: string; body: string }[] = [
  { who: "Buyer agent", cls: "who-buyer", icon: "bot", title: "Plan the dataset", body: "Describe what you need in plain English. The agent drafts tasks, requirements and rewards." },
  { who: "Arc escrow", cls: "who-chain", icon: "lock", title: "Lock USDC", body: "Approve once and the fixed budget is deposited into the escrow contract on Arc." },
  { who: "Contributor agent", cls: "who-contributor", icon: "search", title: "Match work", body: "Contributors say what gear and time they have. The agent finds funded tasks that fit." },
  { who: "Contributor", cls: "who-contributor", icon: "upload", title: "Record & upload", body: "Reserve a task at a fixed reward, capture it on a phone and upload before the deadline." },
  { who: "AI verifier", cls: "who-ai", icon: "eye", title: "Verify automatically", body: "Sampled frames are checked against every requirement and the result is attested." },
  { who: "Arc escrow", cls: "who-chain", icon: "coins", title: "Pay out", body: "Verified work is paid from escrow. Coverage updates and the agent targets the gaps." },
];

/** Landing-page motto: money moves only after verification. */
const LEGACY_LOGIN = process.env.NEXT_PUBLIC_ENABLE_LEGACY_WALLET_LOGIN === "true";

const MOTTO = "Pay for proof, not promises.";

/** Staggered entrance delay for the landing page's rise-in animation. */
const delay = (ms: number) => ({ "--d": `${ms}ms` }) as React.CSSProperties;

/** Consumer-first explanation: the contributor's three steps, in plain words.
 * The blockchain is named only where it earns trust (money set aside, payout). */
const STEPS: { icon: IconName; tone: "chain" | "ai" | "money"; title: string; body: string }[] = [
  { icon: "search", tone: "chain", title: "Pick a task", body: "Tell your agent what you have, like a phone, a towel or ten minutes. It finds paid tasks that fit." },
  { icon: "eye", tone: "ai", title: "Record it", body: "Film the task right in the app. AI checks it against each requirement, usually in under a minute." },
  { icon: "coins", tone: "money", title: "Get paid", body: "Pass the check and the reward is yours, paid in USDC from money that was set aside before you started." },
];

/** Trust strip under the hero: what makes the money safe, in one line each. */
const TRUST: { icon: IconName; title: string; body: string }[] = [
  { icon: "lock", title: "Money set aside first", body: "Every task is funded before you can accept it." },
  { icon: "shield", title: "Checked by AI, not a person", body: "Clear pass/fail reasons for every requirement." },
  { icon: "coins", title: "Paid in digital dollars", body: "USDC on Arc, with sign-in powered by Circle." },
];

/** The contributor journey the landing phone plays on a loop (illustrative). */
const PHONE_CHECKS = ["Hands visible", "Towel folded", "Dark surface"];

function Pipeline() {
  return <div className="pipeline">
    {PIPELINE.map((step, index) => <div className="pipeline-step" key={step.title}>
      <span className={`who ${step.cls}`}>{String(index + 1).padStart(2, "0")} · {step.who}</span>
      <h3><Icon name={step.icon} />{step.title}</h3>
      <p>{step.body}</p>
    </div>)}
  </div>;
}

export default function Workspace() {
  const [session, setSession] = useState<Session>();
  const sessionRef = useRef<Session | undefined>(undefined);
  const attemptRef = useRef(0);
  const [connecting, setConnecting] = useState(false);
  const [authError, setAuthError] = useState("");
  const [role, setRole] = useState<"buyer" | "contributor">("buyer");
  const [view, setView] = useState<View>("overview");
  const [contributorSection, setContributorSection] = useState<"tasks" | "submissions">("tasks");
  const [overview, setOverview] = useState<Overview>();
  const [overviewError, setOverviewError] = useState("");
  const [hasWallet, setHasWallet] = useState(true);
  useEffect(() => { setHasWallet(Boolean((window as Window & { ethereum?: unknown }).ethereum)); }, []);

  function signOut() {
    const previous = sessionRef.current;
    setEmbeddedWalletSender(undefined);
    sessionRef.current = undefined;
    attemptRef.current += 1;
    setSession(undefined);
    setConnecting(false);
    setOverview(undefined);
    setView("overview");
    setRole("buyer");
    setContributorSection("tasks");
    // Remove workspace state immediately; revoke the server token independently.
    // A stale request cannot sign out a newer session (see the token-bound event).
    if (previous) void request("/auth/logout", previous.token, {}).catch(() => {});
  }
  useEffect(
    () => watchWalletChange(
      (event, payload) => { if (sessionRef.current?.method !== "circle" && walletEventEndsSession(event, payload, sessionRef.current?.wallet)) signOut(); },
      (token) => { if (sessionRef.current?.token === token) signOut(); },
    ),
    [],
  );
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(signOut, Math.max(0, session.expiresAt - Date.now()));
    return () => window.clearTimeout(timer);
  }, [session]);
  async function connect() {
    // Ignore double-clicks while a wallet prompt is open; a second request makes
    // MetaMask fail instantly with "request already pending" (-32002).
    if (connecting) return;
    const attempt = ++attemptRef.current;
    setConnecting(true);
    setAuthError("");
    try {
      const authenticated = await authenticate();
      if (attempt !== attemptRef.current) {
        void request("/auth/logout", authenticated.token, {}).catch(() => {});
        return;
      }
      sessionRef.current = authenticated;
      setSession(authenticated);
    } catch (error) {
      if (attempt === attemptRef.current)
        setAuthError(error instanceof Error ? error.message : "Wallet sign-in failed.");
    } finally {
      if (attempt === attemptRef.current) setConnecting(false);
    }
  }
  async function refreshOverview() {
    const active = sessionRef.current;
    if (!active) return;
    setOverviewError("");
    try {
      const result = await request<Overview>("/me/overview", active.token);
      if (sessionRef.current?.token === active.token) setOverview(result);
    } catch (error) {
      if (sessionRef.current?.token === active.token)
        setOverviewError(error instanceof Error ? error.message : "Could not refresh workspace.");
    }
  }
  useEffect(() => { if (session) void refreshOverview(); }, [session?.token, role, view]);
  /** One composer instance lives on the overview (its draft state must survive
   * navigation), so "Create collection" jumps to it rather than duplicating it. */
  function newCollection() {
    setRole("buyer");
    setView("overview");
    window.setTimeout(() => {
      const box = document.getElementById("post-request");
      box?.scrollIntoView({ behavior: "smooth", block: "center" });
      box?.focus({ preventScroll: true });
    }, 50);
  }

  // No marketplace, agent, listing or review component exists before proof of
  // wallet ownership. The API independently rejects every unauthenticated service.
  if (!session)
    return (
      <main className="signin-page theme-dark">
        <header className="landing-nav rise" style={delay(0)}>
          <div className="brand"><span className="mark">F</span>FrameBounty</div>
          <div className="nav-right">
            <span className="environment-badge"><i />{networkName()}</span>
            <a className="nav-cta" href="#signin">Sign in</a>
          </div>
        </header>

        <section className="hero">
          <div className="hero-copy">
            <p className="motto rise" style={delay(60)}>{MOTTO}</p>
            <h1 className="rise" style={delay(140)}>Capture a task.<br /><span>Earn USDC.</span></h1>
            <p className="hero-sub rise" style={delay(220)}>Pick an image or video task, capture what is requested, and submit it for AI verification. Approved work enters its protected payment window. Teams building AI get real-world data they can trust.</p>
            <section id="signin" className="hero-cta rise" style={delay(300)} aria-label="Sign in">
              <CircleLogin authenticated={authenticated => { attemptRef.current += 1; sessionRef.current = authenticated; setSession(authenticated); setAuthError(""); }} />
              {LEGACY_LOGIN && <>
              <div className="or-divider"><span>or</span></div>
              <button className="signin-button wallet-button" onClick={() => void connect()} disabled={connecting}>
                <Icon name="wallet" />{connecting ? "Check your wallet to sign…" : "Connect wallet & sign in"}<Icon name="arrow" />
              </button>
              <p className="signature-note"><Icon name="check" />Wallet sign-in is one message signature. No gas, no payment authority.</p>
              {connecting && <p className="signature-note"><Icon name="info" />Don&apos;t see a popup? Click the MetaMask icon in your browser toolbar; the request may be waiting there.</p>}
              {!hasWallet && <p className="notice">Prefer an existing wallet? Install <a href="https://metamask.io/download/" target="_blank" rel="noreferrer">MetaMask</a>, then reload this page.</p>}
              {authError && <p role="alert" aria-label="Sign-in error" className="error">{authError}</p>}
              <details className="signin-help">
                <summary>First time here?</summary>
                <ol>
                  <li>Sign in with your email. Circle creates your account and wallet for you; there&apos;s nothing to install.</li>
                  <li>Already use MetaMask? Choose &ldquo;Connect wallet&rdquo; and we&apos;ll switch you to {networkName()}.</li>
                  <li>Approve the &ldquo;FrameBounty wallet sign-in&rdquo; message. No gas, no funds.</li>
                  <li>Have several wallet extensions? Disable all but one so they don&apos;t fight over the page.</li>
                </ol>
              </details>
              </>}
              {!LEGACY_LOGIN && <a className="ghost-link" href="#how">See how it works</a>}
            </section>
          </div>

          {/* A browser window playing one contributor's journey on a loop:
              static illustration, not live data, and labelled as such. */}
          <div className="hero-phone rise" style={delay(380)} aria-label="Illustrative example of a contributor getting paid">
            <div className="phone">
              <div className="browser-bar"><span className="dots"><i /><i /><i /></span><span className="url mono">framebounty.app</span></div>
              <div className="phone-screen">
                <div className="ps ps-task">
                  <p className="ps-kicker">Task for you</p>
                  <div className="ps-card">
                    <span className="tag">Video · 15s</span>
                    <strong>Fold a large towel</strong>
                    <span className="ps-reward mono">$0.50</span>
                    <ul>{PHONE_CHECKS.map(c => <li key={c}><Icon name="check" />{c}</li>)}</ul>
                  </div>
                  <span className="ps-button">Accept task</span>
                </div>
                <div className="ps ps-record">
                  <div className="ps-frame"><span className="ps-rec"><i />REC</span><span className="ps-timer mono">0:12</span></div>
                  <span className="ps-shutter" />
                </div>
                <div className="ps ps-check">
                  <p className="ps-kicker"><Icon name="eye" />AI is checking</p>
                  {PHONE_CHECKS.map((c, i) => <div className="ps-line" key={c} style={{ "--i": i } as React.CSSProperties}><span>{c}</span><span className="ps-pass"><Icon name="check" /></span></div>)}
                </div>
                <div className="ps ps-paid">
                  <span className="ps-coin"><Icon name="check" /></span>
                  <p className="ps-kicker">You got paid</p>
                  <p className="ps-amount mono">+$0.50</p>
                  <p className="ps-sub">USDC · sent to your account</p>
                </div>
              </div>
            </div>
            <div className="float-chip chip-verified"><Icon name="shield" />Verified by AI</div>
            <div className="float-chip chip-paid"><Icon name="coins" /><span className="mono">+0.50 USDC</span></div>
            <p className="stage-caption">Illustrative example</p>
          </div>
        </section>

        <section className="trust rise" style={delay(460)} aria-label="Why the money is safe">
          {TRUST.map(t => <div key={t.title}><span className="trust-icon"><Icon name={t.icon} /></span><div><strong>{t.title}</strong><p>{t.body}</p></div></div>)}
        </section>

        <section id="how" className="steps" aria-label="How FrameBounty works">
          <p className="eyebrow">How it works</p>
          <h2>Three steps. <span>No invoices, no chasing.</span></h2>
          <div className="steps-track" aria-hidden="true"><i /></div>
          <div className="steps-grid">
            {STEPS.map((step, index) => <article key={step.title} className="step">
              <span className={`tile tile-${step.tone}`}><Icon name={step.icon} /></span>
              <p className="step-num mono">0{index + 1}</p>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </article>)}
          </div>
        </section>

        <section className="ways" aria-label="Two ways to use FrameBounty">
          <article className="way way-earn">
            <span className="tile tile-money"><Icon name="coins" /></span>
            <h3>I want to earn</h3>
            <ul>
              <li><Icon name="check" />Tasks that fit what you have and your free time</li>
              <li><Icon name="check" />A fixed reward you see before you accept</li>
              <li><Icon name="check" />Paid when your recording passes the AI check</li>
            </ul>
            <a className="way-link" href="#signin">Start earning<Icon name="arrow" /></a>
          </article>
          <article className="way">
            <span className="tile tile-chain"><Icon name="bot" /></span>
            <h3>I need data</h3>
            <ul>
              <li><Icon name="check" />Describe the photos or videos you need in plain English</li>
              <li><Icon name="check" />Set one budget; it&apos;s held safely until work is verified</li>
              <li><Icon name="check" />Pay only for recordings that pass every requirement</li>
            </ul>
            <a className="way-link" href="#signin">Request data<Icon name="arrow" /></a>
          </article>
        </section>

        <footer className="landing-foot">
          <span>{MOTTO}</span>
          <span>AI assists. People collect. Escrow pays. · {networkName()}</span>
        </footer>
      </main>
    );

  const fixture = overview?.fixture;
  const shortWallet = `${session.wallet.slice(0, 6)}…${session.wallet.slice(-4)}`;
  const title = role === "contributor"
    ? contributorSection === "tasks" ? "Find work" : "My submissions"
    : view === "collections" ? "Collections & review" : "Overview";
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => { setRole("buyer"); setView("overview"); }}>
          <span className="mark">F</span>FrameBounty
        </button>
        <div className="workspace-switch" aria-label="Choose workspace">
          <button aria-pressed={role === "buyer"} onClick={() => { setRole("buyer"); setView("overview"); }}>Buyer workspace</button>
          <button aria-pressed={role === "contributor"} onClick={() => { setRole("contributor"); setView("overview"); setContributorSection("tasks"); }}>Contributor workspace</button>
        </div>
        <p className="nav-label">{role === "buyer" ? "BUYER" : "CONTRIBUTOR"}</p>
        <nav className="side-nav" aria-label="Workspace navigation">
          {role === "buyer" ? <>
            <button aria-current={view === "overview" ? "page" : undefined} onClick={() => setView("overview")}><Icon name="grid" />Overview</button>
            <button onClick={newCollection}><Icon name="plus" />Create collection</button>
            <button aria-current={view === "collections" ? "page" : undefined} onClick={() => setView("collections")}>
              <Icon name="folder" />Collections & review
              {overview && overview.awaiting_review > 0 && <span className="nav-count">{overview.awaiting_review}</span>}
            </button>
          </> : <>
            <button aria-current={contributorSection === "tasks" ? "page" : undefined} onClick={() => setContributorSection("tasks")}><Icon name="search" />Find work</button>
            <button aria-current={contributorSection === "submissions" ? "page" : undefined} onClick={() => setContributorSection("submissions")}><Icon name="upload" />My submissions</button>
          </>}
        </nav>
        <div className="sidebar-proof">
          <dl>
            <div><dt>Network</dt><dd>{networkName()}</dd></div>
            <div><dt>Mode</dt><dd>{overview ? fixture ? "Fixture (simulated funds)" : networkName() + " (" + moneyUnit() + ")" : "Checking…"}</dd></div>
            {ESCROW && <div><dt>Escrow contract</dt><dd><ExplorerLink value={ESCROW} kind="address" /></dd></div>}
          </dl>
        </div>
        <div className="sidebar-account">
          <span className="account-avatar">{session.wallet.slice(2, 4).toUpperCase()}</span>
          <div><strong title={session.wallet}>{shortWallet}</strong><span>Wallet verified</span></div>
          <button onClick={signOut} aria-label="Sign out"><Icon name="logout" /></button>
        </div>
      </aside>
      <div className="app-main">
        <header className="workspace-header">
          <div className="breadcrumbs">{role === "buyer" ? "Buyer" : "Contributor"}<span>/</span><strong>{title}</strong></div>
          <div className="header-actions">
            <span className={`environment-badge ${fixture ? "fixture" : ""}`}><i />
              {overview ? fixture ? "Fixture workspace" : networkName() : "Verifying workspace"}</span>
            {role === "buyer" && <button className="primary compact" onClick={newCollection}><Icon name="plus" />New collection</button>}
          </div>
        </header>
        <div className="workspace-content">
          <div className={`environment-notice ${fixture ? "fixture" : ""}`}>
            <Icon name="info" />
            {fixture
              ? "Fixture rewards are simulated and have no monetary value."
              : networkName() + " · Transactions need your wallet authorization. Payment is recognized only after verified receipts."}
          </div>
          {role === "buyer" ? <>
            <section hidden={view !== "overview"} className="stack">
              <div className="page-heading">
                <div>
                  <p className="eyebrow">Buyer workspace</p>
                  <h1>What do you need recorded?</h1>
                  <p>Describe the photos or videos you need. Your agent drafts the request; you approve one budget, held safely until work is verified.</p>
                </div>
                <button className="quiet" onClick={() => void refreshOverview()}>Refresh overview</button>
              </div>
              {overviewError && <p role="alert" className="error">{overviewError}</p>}
              <PostComposer token={session.token} onChanged={refreshOverview} onView={() => setView("collections")} />
              <div className="overview-stats">
                <button onClick={() => setView("collections")}><i className="ov-icon"><Icon name="folder" /></i><span>Collections</span><strong>{overview?.collections ?? "—"}</strong><small>Saved plans and posts</small></button>
                <button onClick={() => setView("collections")}><i className="ov-icon ov-open"><Icon name="search" /></i><span>Open collections</span><strong>{overview?.open_collections ?? "—"}</strong><small>Funded and accepting work</small></button>
                <button onClick={() => setView("collections")}><i className="ov-icon ov-updates"><Icon name="eye" /></i><span>Submission updates</span><strong>{overview?.awaiting_review ?? "—"}</strong><small>Verifying, verified or releasing</small></button>
              </div>
              <details className="how-it-works">
                <summary>How a collection runs, end to end</summary>
                <Pipeline />
              </details>
            </section>
            <section hidden={view !== "collections"} className="stack">
              <div className="page-heading">
                <div>
                  <p className="eyebrow">Collections & review</p>
                  <h1>Your requests</h1>
                  <p>See how close each request is to done. Open one for progress, verified recordings and the payment record.</p>
                </div>
              </div>
              <Posts key={session.wallet} token={session.token} active={view === "collections"} onChanged={refreshOverview} />
            </section>
          </> : (
            <Contributor key={session.wallet} token={session.token} section={contributorSection}
              onWorkReady={() => setContributorSection("submissions")} />
          )}
          <footer className="workspace-footer">
            <span>FrameBounty · Paid for proof, on Arc</span>
            <span>AI assists. People collect. Escrow pays.</span>
          </footer>
        </div>
      </div>
    </main>
  );
}
