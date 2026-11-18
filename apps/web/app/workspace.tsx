"use client";

import { useEffect, useRef, useState } from "react";
import { authenticate, request, watchWalletChange } from "./api";
import Contributor from "./contributor";
import Posts from "./posts";
import PostComposer from "./post-composer";

type Session = { wallet: string; token: string; expiresAt: number };
type Overview = {
  collections: number;
  open_collections: number;
  awaiting_review: number;
  fixture: boolean;
};
type View = "overview" | "create" | "collections";

function Icon({
  name,
}: {
  name:
    | "grid"
    | "plus"
    | "folder"
    | "arrow"
    | "shield"
    | "wallet"
    | "logout"
    | "spark"
    | "check";
}) {
  const paths = {
    grid: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    folder: (
      <path d="M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z" />
    ),
    arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
    shield: (
      <>
        <path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6Z" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    wallet: (
      <>
        <rect x="3" y="5" width="18" height="15" rx="3" />
        <path d="M3 8h18m-5 5h5" />
      </>
    ),
    logout: (
      <>
        <path d="M9 4H5v16h4m5-12 4 4-4 4m-5-4h12" />
      </>
    ),
    spark: (
      <path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z" />
    ),
    check: <path d="m5 12 4 4L19 6" />,
  };
  return (
    <svg
      aria-hidden="true"
      className="icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export default function Workspace() {
  const [session, setSession] = useState<Session>();
  const sessionRef = useRef<Session | undefined>(undefined);
  const attemptRef = useRef(0);
  const [connecting, setConnecting] = useState(false);
  const [authError, setAuthError] = useState("");
  const [role, setRole] = useState<"buyer" | "contributor">("buyer");
  const [view, setView] = useState<View>("overview");
  const [contributorSection, setContributorSection] = useState<
    "tasks" | "submissions"
  >("tasks");
  const [overview, setOverview] = useState<Overview>();
  const [overviewError, setOverviewError] = useState("");

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
    if (previous)
      void request("/auth/logout", previous.token, {}).catch(() => {});
  }
  useEffect(
    () =>
      watchWalletChange(signOut, (token) => {
        if (sessionRef.current?.token === token) signOut();
      }),
    [],
  );
  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(
      signOut,
      Math.max(0, session.expiresAt - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [session]);
  async function connect() {
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
        setAuthError(
          error instanceof Error ? error.message : "Wallet sign-in failed.",
        );
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
        setOverviewError(
          error instanceof Error
            ? error.message
            : "Could not refresh workspace.",
        );
    }
  }
  useEffect(() => {
    if (session) void refreshOverview();
  }, [session?.token, role, view]);
  function newCollection() { setView("create"); }

  // No marketplace, agent, listing or review component exists before proof of
  // wallet ownership. The API independently rejects every unauthenticated service.
  if (!session)
    return (
      <main className="signin-page">
        <section className="signin-story">
          <div className="brand">
            <span className="mark">f</span>FrameBounty
          </div>
          <div className="signin-editorial">
            <p className="eyebrow">CUSTOM DATA. CLEAR COMMITMENTS.</p>
            <h1>
              Better data starts
              <br />
              with people.
            </h1>
            <p className="signin-lead">
              A focused workspace for collecting the examples your next project
              needs.
            </p>
            <div className="signin-roles">
              <div>
                <span className="story-number">01</span>
                <h3>Commission with clarity</h3>
                <p>
                  Shape the plan with your agent. Set a budget and review every
                  contribution.
                </p>
              </div>
              <div>
                <span className="story-number">02</span>
                <h3>Find work that fits</h3>
                <p>
                  Know the reward, requirements and review terms before you
                  commit.
                </p>
              </div>
            </div>
          </div>
          <p className="signin-footnote">
            AI assists. People collect and review.
          </p>
        </section>
        <section className="signin-access" aria-label="Sign in">
          <div className="signin-card">
            <span className="access-icon">
              <Icon name="shield" />
            </span>
            <span className="environment-badge">
              <i />
              Arc testnet
            </span>
            <h2>
              Your workspace,
              <br />
              behind your signature.
            </h2>
            <p>
              Sign in with your wallet to access collections, task opportunities
              and your agents.
            </p>
            <button
              className="primary signin-button"
              onClick={() => void connect()}
              disabled={connecting}
            >
              <Icon name="wallet" />
              {connecting
                ? "Waiting for wallet signature…"
                : "Connect wallet & sign in"}
              <Icon name="arrow" />
            </button>
            <p className="signature-note">
              <Icon name="check" />
              Sign-in is a message signature. It does not authorize payments or
              use gas.
            </p>
            {authError && (
              <p role="alert" aria-label="Sign-in error" className="error">
                {authError}
              </p>
            )}
            <details className="signin-help">
              <summary>First time here?</summary>
              <p>
                Open MetaMask or another compatible browser wallet and select
                Arc Testnet (chain 5042002). Connect your account, then sign the
                one-time FrameBounty message. Workspace access starts only after
                verification.
              </p>
            </details>
          </div>
          <p className="access-footer">
            Testnet funds only · Human review before rewards
          </p>
        </section>
      </main>
    );

  const shortWallet = `${session.wallet.slice(0, 6)}…${session.wallet.slice(-4)}`;
  const title =
    role === "contributor"
      ? contributorSection === "tasks"
        ? "Find work"
        : "My submissions"
      : view === "create"
        ? "New collection"
        : view === "collections"
          ? "Collections & review"
          : "Overview";
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <button className="brand" onClick={() => setView("overview")}>
          <span className="mark">f</span>FrameBounty
        </button>
        <div className="workspace-switch" aria-label="Choose workspace">
          <button
            aria-pressed={role === "buyer"}
            onClick={() => {
              setRole("buyer");
              setView("overview");
            }}
          >
            Buyer workspace
          </button>
          <button
            aria-pressed={role === "contributor"}
            onClick={() => {
              setRole("contributor");
              setView("overview");
              setContributorSection("tasks");
            }}
          >
            Contributor workspace
          </button>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav className="side-nav" aria-label="Workspace navigation">
          {role === "buyer" ? (
            <>
              <button
                aria-current={view === "overview" ? "page" : undefined}
                onClick={() => setView("overview")}
              >
                <Icon name="grid" />
                Overview
              </button>
              <button
                aria-current={view === "create" ? "page" : undefined}
                onClick={newCollection}
              >
                <Icon name="plus" />
                Create collection
              </button>
              <button
                aria-current={view === "collections" ? "page" : undefined}
                onClick={() => setView("collections")}
              >
                <Icon name="folder" />
                Collections & review
                {overview && overview.awaiting_review > 0 && (
                  <span className="nav-count">{overview.awaiting_review}</span>
                )}
              </button>
            </>
          ) : (
            <>
              <button
                aria-current={
                  contributorSection === "tasks" ? "page" : undefined
                }
                onClick={() => setContributorSection("tasks")}
              >
                <Icon name="grid" />
                Find work
              </button>
              <button
                aria-current={
                  contributorSection === "submissions" ? "page" : undefined
                }
                onClick={() => setContributorSection("submissions")}
              >
                <Icon name="folder" />
                My submissions
              </button>
            </>
          )}
        </nav>
        <div className="sidebar-note">
          <Icon name="shield" />
          <p>
            Clear terms.
            <br />
            Human-reviewed work.
            <br />
            Verified transactions.
          </p>
        </div>
        <div className="sidebar-account">
          <span className="account-avatar">
            {session.wallet.slice(2, 4).toUpperCase()}
          </span>
          <div>
            <strong>{shortWallet}</strong>
            <span>Wallet verified</span>
          </div>
          <button onClick={signOut} aria-label="Sign out">
            <Icon name="logout" />
          </button>
        </div>
      </aside>
      <div className="app-main">
        <header className="workspace-header">
          <div className="breadcrumbs">
            Workspace <span>/</span>
            <strong>{title}</strong>
          </div>
          <div className="header-actions">
            <span className="environment-badge">
              <i />
              {overview
                ? overview.fixture
                  ? "Fixture workspace"
                  : "Arc testnet"
                : "Verifying workspace"}
            </span>
            {role === "buyer" && (
              <button className="primary compact" onClick={newCollection}>
                <Icon name="plus" />
                New collection
              </button>
            )}
          </div>
        </header>
        <div className="workspace-content">
          <div className="environment-notice">
            {overview?.fixture
              ? "Fixture rewards are simulated and have no monetary value."
              : "Arc testnet · Transactions need your wallet authorization. Payment is recognized only after verified receipts."}
          </div>
          {role === "buyer" ? (
            <>
              <section hidden={view !== "overview"}>
                <div className="page-heading">
                  <div>
                    <p className="eyebrow">BUYER WORKSPACE</p>
                    <h1>A clear view of your collections.</h1>
                    <p>
                      Turn a data need into a defined plan, then review what
                      comes back.
                    </p>
                  </div>
                  <button
                    className="quiet"
                    onClick={() => void refreshOverview()}
                  >
                    Refresh overview
                  </button>
                </div>
                <div className="overview-stats">
                  <button onClick={() => setView("collections")}>
                    <span>Collections</span>
                    <strong>{overview?.collections ?? "—"}</strong>
                    <small>Your saved plans and collections</small>
                  </button>
                  <button onClick={() => setView("collections")}>
                    <span>Open collections</span>
                    <strong>{overview?.open_collections ?? "—"}</strong>
                    <small>Published and accepting work</small>
                  </button>
                  <button onClick={() => setView("collections")}>
                    <span>Awaiting review</span>
                    <strong>{overview?.awaiting_review ?? "—"}</strong>
                    <small>Contributions that need your decision</small>
                  </button>
                </div>
                {overviewError && (
                  <p role="alert" className="error">
                    {overviewError}
                  </p>
                )}
                <PostComposer token={session.token} onChanged={refreshOverview} onView={() => setView("collections")} />
              </section>
              <section hidden={view !== "create"}>
                <div className="page-heading">
                  <div>
                    <p className="eyebrow">NEW COLLECTION</p>
                    <h1>Define the work. Make the terms clear.</h1>
                    <p>
                      Review every requirement before approving a fixed budget.
                    </p>
                  </div>
                </div>
                <PostComposer token={session.token} onChanged={refreshOverview} onView={() => setView("collections")} />
              </section>
              <section hidden={view !== "collections"}>
                <div className="page-heading">
                  <div>
                    <p className="eyebrow">COLLECTIONS & REVIEW</p>
                    <h1>Your posts. Their status.</h1>
                    <p>
                      See which posts are open, finish publishing drafts and review submissions.
                    </p>
                  </div>
                </div>
                <Posts key={session.wallet} token={session.token} active={view === "collections"} onChanged={refreshOverview} />
              </section>
            </>
          ) : (
            <Contributor
              key={session.wallet}
              token={session.token}
              section={contributorSection}
              onWorkReady={() => setContributorSection("submissions")}
            />
          )}
          <footer className="workspace-footer">
            <span>FrameBounty · Custom data, collected with purpose</span>
            <span>AI assists. People collect and review.</span>
          </footer>
        </div>
      </div>
    </main>
  );
}
