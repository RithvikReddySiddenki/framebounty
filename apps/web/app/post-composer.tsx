"use client";

import { useState } from "react";
import { request, usdc } from "./api";
import type { PlanProposal } from "./agent-pane";
import Funding from "./funding";

type Plan = PlanProposal & { media_type: "image" | "video" };

/** One request becomes an editable post, never an implicit payment authorization. */
export default function PostComposer({ token, onChanged, onView }: {
  token: string; onChanged: () => Promise<void>; onView: () => void;
}) {
  const [message, setMessage] = useState("");
  const [scope, setScope] = useState<string>();
  const [attempt, setAttempt] = useState<{ message: string; id: string }>();
  const [plan, setPlan] = useState<Plan>();
  const [saved, setSaved] = useState<{ id: string; plan_hash: string }>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [approved, setApproved] = useState(false);
  const [published, setPublished] = useState(false);
  const [fixtureConsent, setFixtureConsent] = useState(false);
  const chain = process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true";

  async function generate() {
    setBusy(true); setError("");
    try {
      let id = scope;
      if (!id) { id = (await request<{ id: string }>("/agent-sessions", token, { role: "buyer" })).id; setScope(id); }
      const next = attempt?.message === message ? attempt : { message, id: crypto.randomUUID() };
      setAttempt(next);
      const result = await request<{ data: { plan: Plan } }>(`/agent-sessions/${id}/messages`, token, { message, request_id: next.id });
      const generated = result.data.plan;
      if (!generated) throw new Error("The agent did not produce a post. Describe the subject, image/video type, count and budget.");
      setPlan({ ...generated, media_type: generated.media_type || "video" });
      setSaved(undefined); setApproved(false); setPublished(false); setAttempt(undefined);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not prepare your post"); }
    finally { setBusy(false); }
  }
  async function save() {
    if (!plan || !approved || saved) return;
    setBusy(true); setError("");
    try {
      const result = await request<{ id: string; plan_hash: string }>("/jobs", token, {
        ...plan, budget_atomic: Number(plan.budget_atomic), reward_atomic: Number(plan.reward_atomic),
      });
      setSaved(result); await onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save your post"); }
    finally { setBusy(false); }
  }
  async function simulate() {
    if (!saved || !fixtureConsent) return;
    setBusy(true); setError("");
    try { await request(`/jobs/${saved.id}/fixture-publish`, token, { plan_hash: saved.plan_hash, confirmed: true }); setPublished(true); await onChanged(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not publish fixture post"); }
    finally { setBusy(false); }
  }
  return <section className="panel post-composer" aria-label="Create a post with AI">
    <p className="eyebrow">YOUR BUYER AGENT</p>
    <h2>What do you need collected?</h2>
    <p>Describe the subject, number of images or videos, and your budget. I’ll prepare the post for you.</p>
    <form onSubmit={e => { e.preventDefault(); void generate(); }}>
      <label htmlFor="post-request">Describe your task</label>
      <textarea id="post-request" required minLength={10} maxLength={4000} rows={3} value={message}
        placeholder="I want 20 images of a cat climbing a tree, with a 20 test USDC budget."
        onChange={e => setMessage(e.target.value)} disabled={busy} />
      <button className="primary" disabled={busy || message.trim().length < 10}>{busy ? "Working…" : plan ? "Update post preview" : "Create my post"}</button>
    </form>
    <p className="muted">Up to 20 items. Images: JPEG/PNG. Videos: MP4/MOV, 10–30 seconds. AI verification assists a human payment reviewer.</p>
    {plan && <section className="post-preview" aria-label="Generated post preview">
      <div className="post-tags"><span className="tag">{plan.media_type === "image" ? "Image post" : "Video post"}</span><span className="post-status">{published ? "Open · Simulated funding" : saved ? "Awaiting funding · Not public" : "Preview · Not published"}</span></div>
      <h3>{plan.title}</h3>
      <p>{plan.total} {plan.media_type === "image" ? "images" : "videos"} · {usdc(String(plan.reward_atomic))} test USDC per accepted item · <strong>{usdc(String(plan.budget_atomic))} test USDC budget</strong></p>
      {plan.media_type === "video" && <p>{plan.min_seconds}–{plan.max_seconds} seconds per video</p>}
      <ul>{plan.requirements.map(r => <li key={r.key}>{r.description} · at least {r.minimum}</li>)}</ul>
      <p><strong>Usage rights:</strong> {plan.rights_declaration}</p>
      <p>{plan.review_hours}-hour human review. Your wallet is the authorized reviewer.</p>
      {!saved && <>
        <details><summary>Edit post details</summary>
          <label>Post title<input value={plan.title} onChange={e => { setPlan({ ...plan, title: e.target.value }); setApproved(false); }} /></label>
          <label>Requested usage rights<textarea value={plan.rights_declaration} onChange={e => { setPlan({ ...plan, rights_declaration: e.target.value }); setApproved(false); }} /></label>
          {plan.requirements.map((r, i) => <label key={r.key}>Requirement {i + 1}<textarea value={r.description} onChange={e => { setPlan({ ...plan, requirements: plan.requirements.map((v, n) => n === i ? { ...v, description: e.target.value } : v) }); setApproved(false); }} /></label>)}
          <p>To change the count, media type or budget, update your request above.</p>
        </details>
        <label className="check"><input type="checkbox" checked={approved} onChange={e => setApproved(e.target.checked)} />I approve this post, its usage rights and fixed reward budget.</label>
        <button className="primary" disabled={!approved || busy} onClick={() => void save()}>Approve & save post</button>
      </>}
      {saved && <>
        {chain ? <Funding token={token} jobId={saved.id} planHash={saved.plan_hash} termsApproved onPublished={async () => { setPublished(true); await onChanged(); }} /> : !published && <>
          <label className="check"><input type="checkbox" checked={fixtureConsent} onChange={e => setFixtureConsent(e.target.checked)} />Simulate funding for local testing; rewards have no monetary value.</label>
          <button disabled={!fixtureConsent || busy} onClick={() => void simulate()}>Simulate funding & publish post</button>
        </>}
        <button onClick={onView}>View my posts & status</button>
      </>}
    </section>}
    {error && <p className="error" role="alert">{error} If this was a failed saved request, change your message before retrying.</p>}
  </section>;
}
