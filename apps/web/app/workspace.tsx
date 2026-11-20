"use client";

import { useEffect, useRef, useState } from "react";
import { authenticate, request, walletEventEndsSession, watchWalletChange } from "./api";
import Contributor from "./contributor";
import Posts from "./posts";
import PostComposer from "./post-composer";
import { ExplorerLink, Icon, type IconName } from "./ui";

type Session = { wallet: string; token: string; expiresAt: number };
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
  { who: "Arc escrow", cls: "who-chain", icon: "lock", title: "Lock USDC", body: "Approve once and the fixed budget is deposited into the escrow contract on Arc testnet." },
  { who: "Contributor agent", cls: "who-contributor", icon: "search", title: "Match work", body: "Contributors say what gear and time they have. The agent finds funded tasks that fit." },
  { who: "Contributor", cls: "who-contributor", icon: "upload", title: "Record & upload", body: "Reserve a task at a fixed reward, capture it on a phone and upload before the deadline." },
  { who: "AI verifier", cls: "who-ai", icon: "eye", title: "Verify automatically", body: "Sampled frames are checked against every requirement and the result is attested." },
  { who: "Arc escrow", cls: "who-chain", icon: "coins", title: "Pay out", body: "Verified work is paid from escrow. Coverage updates and the agent targets the gaps." },
];

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
      (event, payload) => { if (walletEventEndsSession(event, payload, sessionRef.current?.wallet)) signOut(); },
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
      <main className="signin-page">
        <section className="signin-story">
          <div className="brand"><span className="mark">F</span>FrameBounty</div>
          <div className="signin-editorial">
            <p className="eyebrow">Agentic data bounties · USDC on Arc</p>
            <h1>Commission real-world data. <em>Pay only for verified work.</em></h1>
            <p className="signin-lead">
              An AI agent turns your request into funded tasks. People capture the data, AI checks every
              submission, and escrow pays contributors in USDC automatically.
            </p>
          </div>
          <Pipeline />
          <p className="signin-footnote">AI assists. People collect. Code and escrow enforce payment.</p>
        </section>
        <section className="signin-access" aria-label="Sign in">
          <div className="signin-card">
            <span className="environment-badge"><i />Arc testnet · chain 5042002</span>
            <h2>Sign in with your wallet</h2>
            <p>One message signature proves you own the address. It doesn&apos;t authorize payments or spend gas.</p>
            <button className="primary signin-button" onClick={() => void connect()} disabled={connecting}>
              <span className="row"><Icon name="wallet" />{connecting ? "Check your wallet to sign…" : "Connect wallet & sign in"}</span>
              <Icon name="arrow" />
            </button>
            {connecting && <p className="signature-note"><Icon name="info" />Don&apos;t see a popup? Click the MetaMask icon in your browser toolbar; the request may be waiting there.</p>}
            {!hasWallet && <p className="notice">No browser wallet detected. Install <a href="https://metamask.io/download/" target="_blank" rel="noreferrer">MetaMask</a>, then reload this page.</p>}
            {authError && <p role="alert" aria-label="Sign-in error" className="error">{authError}</p>}
            <details className="signin-help">
              <summary>First time here?</summary>
              <ol>
                <li>Install MetaMask (or another EVM browser wallet) and unlock it.</li>
                <li>Click sign in. We&apos;ll ask your wallet to add and switch to Arc Testnet (chain 5042002).</li>
                <li>Approve the &ldquo;FrameBounty wallet sign-in&rdquo; message. That&apos;s it: no gas, no funds.</li>
                <li>Have several wallet extensions? Disable all but one so they don&apos;t fight over the page.</li>
              </ol>
            </details>
          </div>
          <p className="access-footer">Testnet funds only · Verified work is paid from escrow</p>
        </section>
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
            <div><dt>Network</dt><dd>Arc testnet · 5042002</dd></div>
            <div><dt>Mode</dt><dd>{overview ? fixture ? "Fixture (simulated funds)" : "Testnet (real test USDC)" : "Checking…"}</dd></div>
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
              {overview ? fixture ? "Fixture workspace" : "Arc testnet" : "Verifying workspace"}</span>
            {role === "buyer" && <button className="primary compact" onClick={newCollection}><Icon name="plus" />New collection</button>}
          </div>
        </header>
        <div className="workspace-content">
          <div className={`environment-notice ${fixture ? "fixture" : ""}`}>
            <Icon name="info" />
            {fixture
              ? "Fixture rewards are simulated and have no monetary value."
              : "Arc testnet · Transactions need your wallet authorization. Payment is recognized only after verified receipts."}
          </div>
          {role === "buyer" ? <>
            <section hidden={view !== "overview"} className="stack">
              <div className="page-heading">
                <div>
                  <p className="eyebrow">Buyer workspace</p>
                  <h1>Commission a dataset</h1>
                  <p>Tell your agent what you need. It drafts the post; you approve the budget once.</p>
                </div>
                <button className="quiet" onClick={() => void refreshOverview()}>Refresh overview</button>
              </div>
              <div className="overview-stats">
                <button onClick={() => setView("collections")}><span>Collections</span><strong>{overview?.collections ?? "—"}</strong><small>Saved plans and posts</small></button>
                <button onClick={() => setView("collections")}><span>Open collections</span><strong>{overview?.open_collections ?? "—"}</strong><small>Funded and accepting work</small></button>
                <button onClick={() => setView("collections")}><span>Submission updates</span><strong>{overview?.awaiting_review ?? "—"}</strong><small>Verifying, verified or releasing</small></button>
              </div>
              {overviewError && <p role="alert" className="error">{overviewError}</p>}
              <PostComposer token={session.token} onChanged={refreshOverview} onView={() => setView("collections")} />
              <details className="how-it-works">
                <summary>How a collection runs, end to end</summary>
                <Pipeline />
              </details>
            </section>
            <section hidden={view !== "collections"} className="stack">
              <div className="page-heading">
                <div>
                  <p className="eyebrow">Collections & review</p>
                  <h1>Your collections</h1>
                  <p>Track each post from plan to payout. Select one to see coverage, submissions and on-chain proof.</p>
                </div>
              </div>
              <Posts key={session.wallet} token={session.token} active={view === "collections"} onChanged={refreshOverview} />
            </section>
          </> : (
            <Contributor key={session.wallet} token={session.token} section={contributorSection}
              onWorkReady={() => setContributorSection("submissions")} />
          )}
          <footer className="workspace-footer">
            <span>FrameBounty · Agentic data bounties on Arc</span>
            <span>AI assists. People collect. Escrow pays.</span>
          </footer>
        </div>
      </div>
    </main>
  );
}
