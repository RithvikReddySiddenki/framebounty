"use client";

import { useEffect, useRef, useState } from "react";
import { request, usdc } from "./api";
import type { PlanProposal } from "./agent-pane";
import Funding from "./funding";
import { Icon, Lifecycle, Requirements, Stat, JOB_STEPS } from "./ui";

type Plan = PlanProposal & { media_type: "image" | "video"; posting_hours?: number; expected_minutes?: number };

const STARTERS = [
  "I need 20 short videos of people folding towels, at least 5 with large towels and 5 on dark surfaces. Budget 20 USDC.",
  "I want 20 images of a cat climbing a tree, with a 20 test USDC budget.",
  "Collect 10 videos of someone pouring water from a bottle into a glass.",
];

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
  // The message currently awaiting an agent reply (drives the typing bubble).
  const [sending, setSending] = useState("");
  const [error, setError] = useState("");
  const [entries, setEntries] = useState<{ id: string; message: string; reply: string }[]>([]);
  const [publishNow, setPublishNow] = useState(false);
  const log = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [entries, sending]);
  const [published, setPublished] = useState(false);
  const chain = process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true";

  async function generate() {
    setBusy(true); setError(""); setSending(message);
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
    finally { setBusy(false); setSending(""); }
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
  const pending = sending;
  const status = published ? chain ? "Open for contributors" : "Open - Simulated funding"
    : saved ? publishNow ? "Awaiting wallet funding" : "Draft - Not public" : "Preview - Not published";
  const progress = published ? { reached: 2, waiting: true } : saved ? { reached: 0, waiting: publishNow } : { reached: -1 };
  const unit = plan?.media_type === "image" ? "images" : "videos";

  return <section className="panel post-composer chat" aria-label="Create a post with AI">
    <div className="chat-head">
      <span className="agent-avatar"><Icon name="bot" /></span>
      <div>
        <p className="eyebrow" style={{ marginBottom: 2 }}>Your buyer agent</p>
        <h2>What do you need collected?</h2>
      </div>
    </div>
    <p className="muted" style={{ marginTop: 10 }}>I&apos;ll ask for anything missing (count, budget, media type), then draft a post you can edit before anything is funded.</p>

    <div ref={log} className="conversation-log" aria-live="polite">
      {entries.map(entry => <article className="conversation-entry" key={entry.id}>
        <p className="bubble me"><span className="who">You</span>{entry.message}</p>
        <p className="bubble agent"><span className="who">Agent</span>{entry.reply}</p>
      </article>)}
      {pending && <article className="conversation-entry">
        <p className="bubble me"><span className="who">You</span>{pending}</p>
        <p className="bubble agent"><span className="who">Agent</span><span className="typing" aria-hidden="true"><i /><i /><i /></span></p>
      </article>}
    </div>

    {entries.length === 0 && !busy && <div className="suggestions" aria-label="Example requests">
      {STARTERS.map(text => <button type="button" key={text} className="chip" onClick={() => setMessage(text)}>{text.length > 64 ? text.slice(0, 62) + "…" : text}</button>)}
    </div>}

    <form className="chat-form" onSubmit={e => { e.preventDefault(); void generate(); }}>
      <label htmlFor="post-request">Describe your task</label>
      <div className="chat-input">
        <textarea id="post-request" required minLength={1} maxLength={4000} rows={2} value={message}
          placeholder="e.g. 20 videos of towel folding, 20 USDC budget"
          onChange={e => setMessage(e.target.value)} disabled={busy}
          onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey && message.trim() && !busy) { e.preventDefault(); void generate(); } }} />
        <button className="primary" disabled={busy || !message.trim()}>{busy ? "Working..." : <><Icon name="send" />Send</>}</button>
      </div>
    </form>
    {busy && <p role="status" className="muted chat-meta">Preparing your post. AI responses can take up to a minute; keep this page open.</p>}
    <p className="muted chat-meta">Up to 20 items · Images: JPEG/PNG · Videos: in-app camera recording, 10–30 s · AI verifies every submission.</p>

    {plan && <section className="post-preview" aria-label="Generated post preview">
      <div className="post-tags">
        <span className="tag">{plan.media_type === "image" ? "Image post" : "Video post"}</span>
        <span className={`post-status ${published ? "is-open" : ""}`}>{status}</span>
      </div>
      <h3>{plan.title}</h3>
      <Lifecycle steps={JOB_STEPS} progress={progress} label="Post lifecycle" />
      <div className="stat-row">
        <Stat icon="grid" label="Items" value={plan.total} unit={unit} />
        <Stat icon="coins" tone="money" label={plan.media_type === "image" ? "Reward / image" : "Reward / clip"} value={usdc(String(plan.reward_atomic))} unit="USDC" />
        <Stat icon="lock" tone="money" label="Total budget" value={usdc(String(plan.budget_atomic))} unit="USDC" />
        {plan.media_type === "video"
          ? <Stat icon="clock" label="Clip length" value={`${plan.min_seconds}–${plan.max_seconds}`} unit="sec" />
          : <Stat icon="clock" label="Open for" value={plan.posting_hours || 24} unit="hrs" />}
      </div>
      <Requirements items={plan.requirements} />
      <details>
        <summary>Usage rights & payment terms</summary>
        <p className="muted"><strong>Usage rights:</strong> {plan.rights_declaration}</p>
        <p className="notice">Publishing locks this budget and these requirements for {plan.posting_hours || 24} hours from the start of wallet publishing. Task estimate: {plan.expected_minutes || 15} minutes; reservations last up to twice that time. After on-chain verification, you have one hour to release a batch early; otherwise the contract permits automatic payment. Originals unlock after confirmed payment.</p>
      </details>
      {!saved && <>
        <details><summary>Edit post details</summary>
          <label>Post open for (hours)<input type="number" min={1} max={720} value={plan.posting_hours || 24} onChange={e => setPlan({ ...plan, posting_hours: Number(e.target.value) })} /></label>
          <label>Expected task time (minutes)<input type="number" min={1} max={720} value={plan.expected_minutes || 15} onChange={e => setPlan({ ...plan, expected_minutes: Number(e.target.value) })} /></label>
          <label>Post title<input value={plan.title} onChange={e => setPlan({ ...plan, title: e.target.value })} /></label>
          <label>Requested usage rights<textarea value={plan.rights_declaration} onChange={e => setPlan({ ...plan, rights_declaration: e.target.value })} /></label>
          {plan.requirements.map((r, i) => <label key={r.key}>Requirement {i + 1}<textarea value={r.description} onChange={e => setPlan({ ...plan, requirements: plan.requirements.map((v, n) => n === i ? { ...v, description: e.target.value } : v) })} /></label>)}
          <p className="muted">To change the count, media type or budget, update your request above.</p>
        </details>
        <p className="muted" style={{ marginTop: 14 }}>Publishing approves the displayed requirements, usage rights and fixed budget. {chain ? "Your wallet will ask for the required transaction authorizations." : "Fixture mode: funding and rewards are simulated and have no monetary value."}</p>
      </>}
      {!published && !publishNow && <div className="post-actions">
        <button className="primary" disabled={busy} onClick={() => void save(true)}><Icon name="lock" />{chain ? "Approve budget & publish" : "Publish simulated post"}</button>
        {!saved && <button disabled={busy} onClick={() => void save(false)}>Save draft instead</button>}
      </div>}
      {saved && <>
        {chain && publishNow && <Funding token={token} jobId={saved.id} planHash={saved.plan_hash} termsApproved autoStart onPublished={async () => { setPublished(true); await onChanged(); }} />}
        <div className="post-actions"><button onClick={onView}>View my posts & status<Icon name="arrow" /></button></div>
      </>}
    </section>}
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
