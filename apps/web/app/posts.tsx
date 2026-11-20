"use client";
import { useEffect, useState } from "react";
import { request, usdc } from "./api";
import Funding from "./funding";
import Reviews from "./reviews";
import RefundUnused from "./refund-unused";
import type { PlanProposal } from "./agent-pane";
import { ExplorerLink, Icon, JOB_STEPS, Lifecycle, Requirements, Stat, jobProgress, short } from "./ui";

type Post = { protection_version?: number; expires_at?: string | null; id: string; title: string; state: string; fixture: boolean; media_type: "image" | "video";
  publication_status: string; open_slots: number; plan: PlanProposal; plan_hash: string; deposited_atomic: string; paid_atomic: string; available_atomic?: string };
const labels: Record<string, string> = { draft: "Draft · Not public", awaiting_funding: "Awaiting funding · Not public", open: "Open for contributors", no_available_tasks: "No available tasks", closed: "Closed", expired: "Expired" };
const ESCROW = process.env.NEXT_PUBLIC_ARC_ESCROW_ADDRESS || "";

/** What the ledger says about a post's money, plus where to verify it. Fixture
 * posts say plainly that nothing is on chain rather than showing fake links. */
function Proof({ post }: { post: Post }) {
  return <div className="proof">
    <h4><Icon name="chain" />{post.fixture ? "Payment record (simulated)" : "Payment record · on Arc"}</h4>
    <dl>
      <dt>Escrow</dt>
      <dd>{post.fixture ? "None. Fixture post: funding is simulated, no transaction exists."
        : ESCROW && post.protection_version === 3 ? <ExplorerLink value={ESCROW} kind="address" /> : `Arc escrow ${post.protection_version ? `V${post.protection_version}` : ""}`.trim()}</dd>
      <dt>Plan hash</dt><dd className="mono" title={post.plan_hash}>{short(post.plan_hash, 10, 8)}</dd>
      <dt>Deposited</dt><dd className="mono">{usdc(post.deposited_atomic)} USDC</dd>
      <dt>Paid out</dt><dd className="mono">{usdc(post.paid_atomic)} USDC</dd>
      {post.available_atomic && <><dt>Uncommitted</dt><dd className="mono">{usdc(post.available_atomic)} USDC</dd></>}
      {post.expires_at && <><dt>Budget locked until</dt><dd>{new Date(post.expires_at).toLocaleString()}</dd></>}
    </dl>
  </div>;
}

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
  async function remove(post: Post) {
    setBusy(true); setError("");
    try { await request(`/jobs/${post.id}/remove`, token, {}); setSelected(undefined); await changed(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not remove this draft"); }
    finally { setBusy(false); }
  }
  const post = posts.find(p => p.id === selected);
  const unit = post?.media_type === "image" ? "images" : "videos";
  return <>
    <div className="post-list-toolbar">
      <p className="muted">Only funded posts with available tasks are visible to contributors.</p>
      <button disabled={busy} onClick={() => void refresh()}>{busy ? "Refreshing…" : "Refresh posts"}</button>
    </div>
    {!busy && posts.length === 0 && !error && <div className="empty"><Icon name="folder" /><p>No posts yet. Describe a task to your buyer agent on the Overview to create one.</p></div>}
    <div className="post-list">{posts.map(p => <button key={p.id} className={`post-card ${selected === p.id ? "selected" : ""}`} aria-pressed={selected === p.id} onClick={() => setSelected(p.id)}>
      <div className="post-tags">
        <span className="tag">{p.media_type === "image" ? "Image post" : "Video post"}</span>
        <span className={`post-status ${p.publication_status === "open" ? "is-open" : ""}`}>{labels[p.publication_status] || p.publication_status.replaceAll("_", " ")}</span>
        {p.fixture && <span className="tag">Simulated funding</span>}
      </div>
      <h3>{p.title}</h3>
      <p className="mono">{p.plan.total} items · {usdc(String(p.plan.budget_atomic))} USDC budget · {p.open_slots} available slots</p>
      <Lifecycle steps={JOB_STEPS} progress={jobProgress(p)} label={`Lifecycle for ${p.title}`} />
      <span>View post & submissions →</span>
    </button>)}</div>
    {post && <section className="panel post-detail" aria-label="Your post details">
      {post.state === "draft" && post.deposited_atomic === "0" && <div className="spread">
        <p className="muted">Not published yet? Remove this draft if no deposit is pending. Close any open wallet prompts first.</p>
        <button disabled={busy} onClick={() => void remove(post)}>Remove unfunded post</button>
      </div>}
      <div className="spread">
        <div>
          <div className="post-tags">
            <span className="tag">{post.media_type === "image" ? "Image post" : "Video post"}</span>
            <span className={`post-status ${post.publication_status === "open" ? "is-open" : ""}`}>{labels[post.publication_status] || post.publication_status}</span>
          </div>
          <h2>{post.title}</h2>
        </div>
      </div>
      <Lifecycle steps={JOB_STEPS} progress={jobProgress(post)} label="Post lifecycle" />
      <div className="stat-row">
        <Stat icon="grid" label="Items" value={post.plan.total} unit={unit} />
        <Stat icon="coins" tone="money" label={post.media_type === "image" ? "Reward / image" : "Reward / clip"} value={usdc(String(post.plan.reward_atomic))} unit="USDC" />
        <Stat icon="lock" tone="money" label="Funded" value={usdc(post.deposited_atomic)} unit="USDC" />
        <Stat icon="check" tone="money" label="Paid" value={usdc(post.paid_atomic)} unit="USDC" />
        <Stat icon="search" label="Available slots" value={post.open_slots} />
      </div>
      {post.protection_version === 3 && <p className="notice">Protected budget locked until {post.expires_at ? new Date(post.expires_at).toLocaleString() : "publication expires"}. Requirements are fixed. Verified work pays automatically after one hour.</p>}
      <Reviews key={`reviews-${post.id}`} token={token} jobId={post.id} onChanged={changed} />
      <Requirements items={post.plan.requirements} note={post.media_type === "video" ? `${post.plan.min_seconds}–${post.plan.max_seconds} seconds per video · AI checks each one` : undefined} />
      <details><summary>Usage rights</summary><p className="muted">{post.plan.rights_declaration}</p></details>
      <Proof post={post} />
      {post.state === "draft" && <p className="notice">This post is saved privately. Complete funding to make tasks visible to contributors.</p>}
      {post.publication_status === "no_available_tasks" && <p className="notice">The collection is funded, but tasks are claimed, expired or no longer covered by available funds. Review submissions or ask the collection agent to commission the next batch.</p>}
      {post.state === "draft" && process.env.NEXT_PUBLIC_ENABLE_CHAIN_FUNDING === "true" && <Funding key={`funding-${post.id}`} token={token} jobId={post.id} planHash={post.plan_hash} onPublished={changed} />}
      {post.protection_version === 3 && post.expires_at && new Date(post.expires_at).getTime() <= Date.now() && <RefundUnused token={token} jobId={post.id} onChanged={changed} />}
    </section>}
    {error && <p className="error" role="alert">{error}</p>}
  </>;
}
