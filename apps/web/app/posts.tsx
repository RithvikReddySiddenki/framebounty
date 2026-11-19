"use client";
import { useEffect, useState } from "react";
import { request, usdc } from "./api";
import Funding from "./funding";
import Reviews from "./reviews";
import RefundUnused from "./refund-unused";
import type { PlanProposal } from "./agent-pane";

type Post = { protection_version?: number; expires_at?: string | null;  id: string; title: string; state: string; fixture: boolean; media_type: "image" | "video";
  publication_status: string; open_slots: number; plan: PlanProposal; plan_hash: string; deposited_atomic: string; paid_atomic: string };
const labels: Record<string, string> = { draft: "Draft · Not public", awaiting_funding: "Awaiting funding · Not public", open: "Open for contributors", no_available_tasks: "No available tasks", closed: "Closed", expired: "Expired" };

export default function Posts({ token, active, onChanged }: { token: string; active: boolean; onChanged: () => Promise<void> }) {
  const [posts, setPosts] = useState<Post[]>([]);
  const [selected, setSelected] = useState<string>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true); setError("");
    try { setPosts((await request<{ jobs: Post[] }>("/me/jobs", token)).jobs); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not load your posts"); }
    finally { setBusy(false); }
  }
  useEffect(() => { if (active) void refresh(); }, [active, token]);
  async function changed() { await refresh(); await onChanged(); }
  const post = posts.find(p => p.id === selected);
  return <>
    <div className="post-list-toolbar"><p>Your posts load automatically. Only funded posts with available tasks are open.</p><button disabled={busy} onClick={() => void refresh()}>{busy ? "Refreshing…" : "Refresh posts"}</button></div>
    {!busy && posts.length === 0 && !error && <p className="panel">No posts yet. Describe a task to your buyer agent to create one.</p>}
    <div className="post-list">{posts.map(p => <button key={p.id} className={`post-card ${selected === p.id ? "selected" : ""}`} aria-pressed={selected === p.id} onClick={() => setSelected(p.id)}>
      <div className="post-tags"><span className="tag">{p.media_type === "image" ? "Image post" : "Video post"}</span><span className={`post-status ${p.publication_status === "open" ? "is-open" : ""}`}>{labels[p.publication_status] || p.publication_status.replaceAll("_", " ")}</span>{p.fixture && <span className="tag">Simulated funding</span>}</div>
      <h3>{p.title}</h3><p>{p.plan.total} items · {usdc(String(p.plan.budget_atomic))} test USDC budget · {p.open_slots} available slots</p>
      <span>View post & submissions →</span>
    </button>)}</div>
    {post && <section className="panel post-detail" aria-label="Your post details">
      <span className="tag">{post.media_type === "image" ? "Image post" : "Video post"}</span>
      <h2>{post.title}</h2>
      {post.protection_version === 3 && <p className="notice">Protected budget locked until {post.expires_at ? new Date(post.expires_at).toLocaleString() : "publication expires"}. Requirements are fixed. Verified work pays automatically after one hour.</p>}<p className="post-status">{labels[post.publication_status] || post.publication_status}</p>
      <p>{post.plan.total} {post.media_type === "image" ? "images" : "videos"} · {usdc(String(post.plan.reward_atomic))} test USDC per accepted item</p>
      {post.media_type === "video" && <p>{post.plan.min_seconds}–{post.plan.max_seconds} seconds per video</p>}
      <ul>{post.plan.requirements.map(r => <li key={r.key}>{r.description} · at least {r.minimum}</li>)}</ul>
      <p><strong>Usage rights:</strong> {post.plan.rights_declaration}</p>
      <p>Funded: {usdc(post.deposited_atomic)} · Paid: {usdc(post.paid_atomic)} test USDC</p>
      {post.state === "draft" && <p>This post is saved privately. Complete funding to make tasks visible to contributors.</p>}
      {post.publication_status === "no_available_tasks" && <p>The collection is funded, but tasks are claimed, expired or no longer covered by available funds. Review submissions or ask the collection agent to commission the next batch.</p>}
      {post.state === "draft" && process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true" && <Funding key={`funding-${post.id}`} token={token} jobId={post.id} planHash={post.plan_hash} onPublished={changed} />}
      {post.protection_version === 3 && post.expires_at && new Date(post.expires_at).getTime() <= Date.now() && <RefundUnused token={token} jobId={post.id} onChanged={changed} />}
      <Reviews key={`reviews-${post.id}`} token={token} jobId={post.id} onChanged={changed} />
    </section>}
    {error && <p className="error" role="alert">{error}</p>}
  </>;
}
