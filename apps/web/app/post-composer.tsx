"use client";

import { useEffect, useRef, useState } from "react";
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
  const [entries, setEntries] = useState<{ id: string; message: string; reply: string }[]>([]);
  const [publishNow, setPublishNow] = useState(false);
  const log = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [entries]);
  const [published, setPublished] = useState(false);
  const chain = process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true";

  async function generate() {
    setBusy(true); setError("");
    try {
      let id = scope;
      if (!id) { id = (await request<{ id: string }>("/chat-sessions", token, { role: "buyer" })).id; setScope(id); }
      const next = attempt?.message === message ? attempt : { message, id: crypto.randomUUID() };
      setAttempt(next);
      const result = await request<{ reply: string; data: { plan?: Plan } }>(`/chat-sessions/${id}/messages`, token, { message, request_id: next.id });
      const generated = result.data.plan;
      setEntries(current => [...current.filter(e => e.id !== next.id), { id: next.id, message, reply: result.reply }]);
      setPlan(generated ? { ...generated, media_type: generated.media_type || "video" } : undefined);
      setSaved(undefined); setPublished(false); setPublishNow(false); setAttempt(undefined); setMessage("");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not prepare your post"); }
    finally { setBusy(false); }
  }
  async function save(publish = true) {
    if (!plan || busy) return;
    setBusy(true); setError("");
    try {
      if (![plan.budget_atomic, plan.reward_atomic].every(value => /^[0-9]+$/.test(String(value)) && Number.isSafeInteger(Number(value))))
        throw new Error("This amount exceeds the editor's exact integer range. Ask the agent for a smaller budget.");
      const result = saved || await request<{ id: string; plan_hash: string }>("/jobs", token, {
        ...plan, budget_atomic: Number(plan.budget_atomic), reward_atomic: Number(plan.reward_atomic),
      });
      setSaved(result);
      if (publish && !chain) {
        await request(`/jobs/${result.id}/fixture-publish`, token, { plan_hash: result.plan_hash, confirmed: true });
        setPublished(true);
      }
      if (publish && chain) setPublishNow(true);
      await onChanged();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save your post"); }
    finally { setBusy(false); }
  }
  return <section className="panel post-composer" aria-label="Create a post with AI">
    <p className="eyebrow">YOUR BUYER AGENT</p>
    <h2>What do you need collected?</h2>
    <p>Tell me what you need. I'll ask for any missing details and prepare your post.</p>
    <div ref={log} className="conversation-log" aria-live="polite">{entries.map(entry => <article className="conversation-entry" key={entry.id}><p><strong>You:</strong> {entry.message}</p><p><strong>Agent:</strong> {entry.reply}</p></article>)}</div>
    <form onSubmit={e => { e.preventDefault(); void generate(); }}>
      <label htmlFor="post-request">Describe your task</label>
      <textarea id="post-request" required minLength={1} maxLength={4000} rows={3} value={message}
        placeholder="I want 20 images of a cat climbing a tree, with a 20 test USDC budget."
        onChange={e => setMessage(e.target.value)} disabled={busy} />
      <button className="primary" disabled={busy || !message.trim()}>{busy ? "Working..." : "Send"}</button>
    </form>
    <p className="muted">Up to 20 items. Images: JPEG/PNG. Videos: MP4/MOV, 10–30 seconds. AI verification assists a human payment reviewer.</p>
    {plan && <section className="post-preview" aria-label="Generated post preview">
      <div className="post-tags"><span className="tag">{plan.media_type === "image" ? "Image post" : "Video post"}</span><span className="post-status">{published ? chain ? "Open for contributors" : "Open - Simulated funding" : saved ? publishNow ? "Awaiting wallet funding" : "Draft - Not public" : "Preview - Not published"}</span></div>
      <h3>{plan.title}</h3>
      <p>{plan.total} {plan.media_type === "image" ? "images" : "videos"} · {usdc(String(plan.reward_atomic))} test USDC per accepted item · <strong>{usdc(String(plan.budget_atomic))} test USDC budget</strong></p>
      {plan.media_type === "video" && <p>{plan.min_seconds}–{plan.max_seconds} seconds per video</p>}
      <ul>{plan.requirements.map(r => <li key={r.key}>{r.description} · at least {r.minimum}</li>)}</ul>
      <p><strong>Usage rights:</strong> {plan.rights_declaration}</p>
      <p>{plan.review_hours}-hour funds-release window. AI verifies submissions; your wallet makes the final payment decision.</p>
      {!saved && <>
        <details><summary>Edit post details</summary>
          <label>Post title<input value={plan.title} onChange={e => { setPlan({ ...plan, title: e.target.value });  }} /></label>
          <label>Requested usage rights<textarea value={plan.rights_declaration} onChange={e => { setPlan({ ...plan, rights_declaration: e.target.value });  }} /></label>
          {plan.requirements.map((r, i) => <label key={r.key}>Requirement {i + 1}<textarea value={r.description} onChange={e => { setPlan({ ...plan, requirements: plan.requirements.map((v, n) => n === i ? { ...v, description: e.target.value } : v) });  }} /></label>)}
          <p>To change the count, media type or budget, update your request above.</p>
        </details>
        <p>Publishing approves the displayed requirements, usage rights and fixed budget. {chain ? "Your wallet will ask for the required transaction authorizations." : "Fixture mode: funding and rewards are simulated and have no monetary value."}</p>
      </>}
      {!published && !publishNow && <div className="post-actions">
        <button className="primary" disabled={busy} onClick={() => void save(true)}>{chain ? "Approve budget & publish" : "Publish simulated post"}</button>
        {!saved && <button disabled={busy} onClick={() => void save(false)}>Save draft instead</button>}
      </div>}
      {saved && <>
        {chain && publishNow && <Funding token={token} jobId={saved.id} planHash={saved.plan_hash} termsApproved autoStart onPublished={async () => { setPublished(true); await onChanged(); }} />}
        <button onClick={onView}>View my posts & status</button>
      </>}
    </section>}
    {error && <p className="error" role="alert">{error} If this was a failed saved request, change your message before retrying.</p>}
  </section>;
}
