"use client";
import { useEffect, useRef, useState } from "react";
import { request, usdc } from "./api";
import { BuyerReputation } from "./reputation";

type Task = { job_id: string; task_id: string; title: string; media_type: string; version: number; reward_atomic: string;
  minutes: number; deadline: string; fixture: boolean; requirements: { key: string; description: string }[];
  rights_declaration: string; review_hours: number; reviewer: string; explanation: string };
type Reply = { reply: string; provider_mode: string; data: { facts: { equipment?: string[]; minutes?: number; no_time_limit?: boolean }; tasks?: Task[] } };
type Entry = { id: string; message: string; result: Reply };

/** Chat collects explicit capabilities; only a displayed task click reserves work. */
export default function WorkChat({ token, onReserved }: { token: string; onReserved: () => Promise<void> }) {
  const [sid, setSid] = useState<string>();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [prepared, setPrepared] = useState<{ task: string; deadline: string }>();
  const attempt = useRef<{ id: string; message: string } | undefined>(undefined);
  const reservation = useRef<{ task: string; body: Record<string, unknown> } | undefined>(undefined);
  const log = useRef<HTMLDivElement | null>(null);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [entries]);
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const result = await request<{ sessions: { id: string }[] }>("/chat-sessions?role=contributor", token);
        if (!result.sessions[0]) return;
        const previous = await request<{ id: string; turns: Entry[] }>(`/agent-sessions/${result.sessions[0].id}`, token);
        if (active) { setSid(previous.id); setEntries(previous.turns); }
      } catch (err) { if (active) setError(err instanceof Error ? err.message : "Could not restore your conversation"); }
      finally { if (active) setLoading(false); }
    })();
    return () => { active = false; };
  }, [token]);
  async function send() {
    if (busy || loading || !message.trim()) return;
    setBusy(true); setError("");
    try {
      const id = sid || (await request<{ id: string }>("/chat-sessions", token, { role: "contributor" })).id;
      setSid(id);
      const next = attempt.current?.message === message ? attempt.current : { id: crypto.randomUUID(), message };
      attempt.current = next;
      const result = await request<Reply>(`/chat-sessions/${id}/messages`, token, { message, request_id: next.id });
      setEntries(current => [...current.filter(e => e.id !== next.id), { id: next.id, message, result }]);
      setMessage(""); attempt.current = undefined;
    } catch (err) { setError(err instanceof Error ? err.message : "Could not search for work"); }
    finally { setBusy(false); }
  }
  async function reserve(task: Task) {
    setBusy(true); setError("");
    try {
      if (reservation.current?.task !== task.task_id) {
        const confirmation = await request<{ confirmation_id: string; version: number; reward_atomic: string; reservation_expires_at: string }>(`/tasks/${task.task_id}/confirmation`, token, {});
        if (confirmation.version !== task.version || confirmation.reward_atomic !== task.reward_atomic)
          throw new Error("This task changed. Ask me to find current work before reserving.");
        reservation.current = { task: task.task_id, body: { confirmation_id: confirmation.confirmation_id,
          version: confirmation.version, reward_atomic: confirmation.reward_atomic, task_id: task.task_id,
          confirmed: true, idempotency_key: crypto.randomUUID() } };
        setPrepared({ task: task.task_id, deadline: confirmation.reservation_expires_at });
        return;
      }
      await request("/reservations", token, reservation.current.body);
      await onReserved();
      reservation.current = undefined; setPrepared(undefined);
    } catch (err) { setError(err instanceof Error ? err.message : "This task is no longer available; ask me to search again"); }
    finally { setBusy(false); }
  }
  const latest = entries[entries.length - 1]?.result;
  return <section className="work-chat" aria-label="Contributor chat">
    <p>Tell me what you have and what you would like to do. I’ll ask for anything missing and find matching funded tasks.</p>
    <div ref={log} className="conversation-log" aria-live="polite">{entries.map(entry => <article className="conversation-entry" key={entry.id}>
      <p><strong>You:</strong> {entry.message}</p><p><strong>Agent:</strong> {entry.result.reply}</p>
      {entry.result.provider_mode === "fixture" && <small>Fixture conversation · Listings come from the database; no live AI interpretation.</small>}
    </article>)}</div>
    {latest?.data.facts.equipment && <p className="muted">Using: {latest.data.facts.equipment.join(", ") || "no equipment"}{latest.data.facts.no_time_limit ? " · no time filter" : latest.data.facts.minutes ? ` · ${latest.data.facts.minutes} minutes` : ""}. Tell me if this changes.</p>}
    {latest?.data.tasks?.map(task => <article className="panel agent-task" key={task.task_id}>
      <span className="tag">{task.media_type === "image" ? "Image post" : "Video post"}</span>
      <h3>{task.title}</h3><p><strong>{usdc(task.reward_atomic)} {task.fixture ? "fixture" : "test"} USDC</strong> per accepted item · about {task.minutes} minutes</p>
      <p>{task.explanation}</p><BuyerReputation token={token} jobId={task.job_id} />
      {prepared?.task === task.task_id && <p className="notice">Accept {usdc(task.reward_atomic)} {task.fixture ? "simulated fixture" : "test"} USDC for these fixed requirements. Upload deadline: {new Date(prepared.deadline).toLocaleString()}. Your deadline will not extend after accepting.</p>}
      <p>Reserve for up to {2 * task.minutes} minutes. Listing closes {new Date(task.deadline).toLocaleString()}.</p>
      <details><summary>Requirements & usage rights</summary><ul>{task.requirements.map(r => <li key={r.key}>{r.description}</li>)}</ul><p>{task.rights_declaration}</p><p>Reviewer: {task.reviewer}. Payment requires passing AI verification and is not guaranteed by reservation; protected posts then pay automatically after a one-hour payment window.</p></details>
      <button className="primary" disabled={busy} onClick={() => void reserve(task)}>{prepared?.task === task.task_id ? "Accept fixed terms for" : "Review reservation for"} {usdc(task.reward_atomic)} {task.fixture ? "fixture" : "test"} USDC</button>
    </article>)}
    <form onSubmit={e => { e.preventDefault(); void send(); }}>
      <label htmlFor="work-message">Message your work agent</label>
      <textarea id="work-message" value={message} rows={3} maxLength={4000} placeholder="I have a phone and a cat. What tasks can I do?" onChange={e => setMessage(e.target.value)} disabled={busy || loading} />
      <button className="primary" disabled={busy || loading || !message.trim()}>{loading ? "Restoring chat…" : busy ? "Working…" : "Send"}</button>
    </form>
    <details><summary>Conversation options</summary><button disabled={busy || loading} onClick={() => { setSid(undefined); setEntries([]); setMessage(""); setError(""); attempt.current = undefined; reservation.current = undefined; }}>Start a new work search</button></details>
    {error && <p className="error" role="alert">{error}</p>}
  </section>;
}
