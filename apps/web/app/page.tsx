"use client";

import { useState } from "react";

const requirements = ["20 accepted videos", "10–30 seconds each", "5+ large-towel examples", "5+ dark-surface examples"];

export default function Home() {
  const [role, setRole] = useState<"buyer" | "contributor">("buyer");
  const [prompt, setPrompt] = useState("We need 20 videos of people folding towels, each 10–30 seconds, including at least five using large towels and five on dark surfaces. Keep contributor rewards under 20 USDC.");
  const [showPlan, setShowPlan] = useState(false);
  return <main>
    <header><a className="brand" href="/" aria-label="FrameBounty home"><span className="mark">F</span>FrameBounty</a><span className="network">◌ Arc testnet · not connected</span></header>
    <div className="notice"><strong>Development preview</strong> · Example plan only. No wallet connected, funded listings, reservations, or payments.</div>
    <nav aria-label="Workspace"><button aria-pressed={role === "buyer"} onClick={() => setRole("buyer")}>Buyer workspace</button><button aria-pressed={role === "contributor"} onClick={() => setRole("contributor")}>Contributor workspace</button></nav>
    {role === "buyer" ? <>
      <section className="hero"><div><p className="eyebrow">PURPOSE-BUILT DATA, HUMAN-COLLECTED</p><h1>The data you need.<br /><span>The work that matters.</span></h1><p className="intro">Describe your dataset. Shape the collection plan. Review real contributions before rewards are released.</p></div><aside className="flow"><span>01 / Define the dataset</span><span>02 / Fund a collection</span><span>03 / Review & reward</span><span>04 / Build your next batch ↗</span></aside></section>
      <section className="workspace"><div className="panel compose"><p className="eyebrow">BUYER AGENT</p><h2>What are we collecting?</h2><label htmlFor="request">Dataset request</label><textarea id="request" value={prompt} onChange={e => {setPrompt(e.target.value); setShowPlan(false);}} rows={5} /><div className="compose-footer"><span>Robotics video · first supported workflow</span><button className="primary" onClick={() => setShowPlan(true)}>View example plan ↗</button></div><p className="muted">This preview displays a fixed towel-folding example. It does not interpret your request with AI.</p></div>
      <aside className="panel"><p className="eyebrow">COLLECTION PRINCIPLES</p><h2>Clear terms.<br />Real commitments.</h2><ul className="principles"><li>Funded before work begins</li><li>Fixed rewards when reserved</li><li>Human approval before payout</li><li>Every accepted clip counts once</li></ul><p className="muted">One clip can satisfy several category requirements. Pending work is tracked separately from accepted data.</p></aside></section>
      {showPlan && <section className="panel plan" aria-live="polite"><p className="eyebrow">ILLUSTRATIVE PLAN · NOT CONFIRMED</p><h2>Towel-folding demonstrations</h2><div className="metrics"><div><strong>20</strong><span>target clips</span></div><div><strong>1 USDC</strong><span>per accepted clip</span></div><div><strong>20 USDC</strong><span>reward budget</span></div><div><strong>72 hours</strong><span>proposed review window</span></div></div><div className="chips">{requirements.map(r => <span key={r}>{r}</span>)}</div><p>The reviewer must confirm a complete towel fold. Large towels and dark surfaces need buyer-approved descriptions and reference examples. Gas and inference are separate from rewards.</p><p className="muted">Next: editable terms, usage rights, wallet authentication and verified funding. Reviewer rejection or an abandoned review may release the reward after timeout; payment is not guaranteed without approval.</p><button disabled>Funding unavailable in this preview</button></section>}
    </> : <section className="panel contributor"><p className="eyebrow">CONTRIBUTOR AGENT</p><h1>Good work starts<br />with a good fit.</h1><p className="intro">Find funded tasks that fit your time, equipment, and skills.</p><div className="empty"><span className="empty-icon">⌕</span><h2>Task search is being connected</h2><p>No funded listings are available in this development preview. Recommendations will come from actual task records.</p><p className="muted">You’ll review the reward, requirements, expiry and reviewer terms before confirming a specific reservation.</p></div></section>}
    <footer><span>FrameBounty / Custom data, with purpose.</span><span>AI assists. People collect and review.</span></footer>
  </main>;
}
