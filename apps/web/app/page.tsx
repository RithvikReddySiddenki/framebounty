"use client";

import { useEffect, useState } from "react";
import { authenticate, watchWalletChange } from "./api";
import Contributor from "./contributor";
import BuyerPlan from "./buyer-plan";

const requirements = ["20 accepted videos", "10–30 seconds each", "5+ large-towel examples", "5+ dark-surface examples"];

export default function Home() {
  const [session, setSession] = useState<{ wallet: string; token: string }>();
  const [authError, setAuthError] = useState("");
  const [connecting, setConnecting] = useState(false);
  useEffect(() => watchWalletChange(() => setSession(undefined)), []);
  async function connect() {
    setConnecting(true); setAuthError("");
    try { setSession(await authenticate()); } catch (err) { setAuthError(err instanceof Error ? err.message : "Wallet sign-in failed."); }
    finally { setConnecting(false); }
  }
  const [role, setRole] = useState<"buyer" | "contributor">("buyer");
  const [prompt, setPrompt] = useState("We need 20 videos of people folding towels, each 10–30 seconds, including at least five using large towels and five on dark surfaces. Keep contributor rewards under 20 USDC.");
  const [showPlan, setShowPlan] = useState(false);
  return <main>
    <header><a className="brand" href="/" aria-label="FrameBounty home"><span className="mark">F</span>FrameBounty</a><button className="network" onClick={() => session ? setSession(undefined) : void connect()} disabled={connecting}>{connecting ? "Awaiting wallet…" : session ? `${session.wallet.slice(0, 6)}…${session.wallet.slice(-4)} · Disconnect` : "Connect wallet · Arc testnet"}</button></header>
    <div className="notice"><strong>Development preview</strong> · Search reads database records. Fixture funds are simulated. Live payments and uploads are not connected.</div>
    {authError && <p role="alert" className="error">{authError}</p>}
    <nav aria-label="Workspace"><button aria-pressed={role === "buyer"} onClick={() => setRole("buyer")}>Buyer workspace</button><button aria-pressed={role === "contributor"} onClick={() => setRole("contributor")}>Contributor workspace</button></nav>
    {role === "buyer" ? <>
      <section className="hero"><div><p className="eyebrow">PURPOSE-BUILT DATA, HUMAN-COLLECTED</p><h1>The data you need.<br /><span>The work that matters.</span></h1><p className="intro">Describe your dataset. Shape the collection plan. Review real contributions before rewards are released.</p></div><aside className="flow"><span>01 / Define the dataset</span><span>02 / Fund a collection</span><span>03 / Review & reward</span><span>04 / Build your next batch ↗</span></aside></section>
      <section className="workspace"><div className="panel compose"><p className="eyebrow">BUYER AGENT</p><h2>What are we collecting?</h2><label htmlFor="request">Dataset request</label><textarea id="request" value={prompt} onChange={e => {setPrompt(e.target.value); setShowPlan(false);}} rows={5} /><div className="compose-footer"><span>Robotics video · first supported workflow</span><button className="primary" onClick={() => setShowPlan(true)}>View example plan ↗</button></div><p className="muted">This preview displays a fixed towel-folding example. It does not interpret your request with AI.</p></div>
      <aside className="panel"><p className="eyebrow">COLLECTION PRINCIPLES</p><h2>Clear terms.<br />Real commitments.</h2><ul className="principles"><li>Funded before work begins</li><li>Fixed rewards when reserved</li><li>Human approval before payout</li><li>Every accepted clip counts once</li></ul><p className="muted">One clip can satisfy several category requirements. Pending work is tracked separately from accepted data.</p></aside></section>
      {showPlan && <section className="panel plan"><p className="eyebrow">EXAMPLE STARTING POINT</p><div className="chips">{requirements.map(r => <span key={r}>{r}</span>)}</div><BuyerPlan key={session?.wallet || "anonymous"} token={session?.token} /></section>}
    </> : <Contributor key={session?.wallet || "anonymous"} token={session?.token} />}
    <footer><span>FrameBounty / Custom data, with purpose.</span><span>AI assists. People collect and review.</span></footer>
  </main>;
}
