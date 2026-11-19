"use client";
import { useEffect, useRef, useState } from "react";
import { request, sendWalletTransaction } from "./api";
import { publishApprovedPlan, type FundingStep, type PendingFunding } from "./publishing";

type Rating = { supported: boolean; target?: string; role?: string; up?: number; down?: number; vote?: number; eligible?: boolean; notice: string; escrow?: string };

export function BuyerReputation({ token, jobId }: { token: string; jobId: string }) {
  const [rating, setRating] = useState<Rating>();
  useEffect(() => { let active = true; request<Rating>(`/jobs/${jobId}/reputation`, token).then(r => { if (active) setRating(r); }).catch(() => {}); return () => { active = false; }; }, [token, jobId]);
  return <p className="muted">{rating?.supported ? `Buyer reputation: ${rating.up} up / ${rating.down} down · confirmed paid trades on this escrow` : rating?.notice || "Buyer reputation unavailable"}</p>;
}

export default function Reputation({ token, submissionId }: { token: string; submissionId: string }) {
  const [rating, setRating] = useState<Rating>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const running = useRef(false);
  const controller = useRef<AbortController | undefined>(undefined);
  const key = `framebounty:rating:${submissionId}`;
  async function load() { setRating(await request<Rating>(`/submissions/${submissionId}/reputation`, token)); }
  useEffect(() => { let active = true; request<Rating>(`/submissions/${submissionId}/reputation`, token).then(r => { if (active) setRating(r); }).catch(() => { if (active) setError("Reputation is temporarily unavailable."); }); return () => { active = false; controller.current?.abort(); }; }, [token, submissionId]);
  async function vote(value: number) {
    if (running.current) return;
    running.current = true; setBusy(true); setError("");
    const active = new AbortController(); controller.current = active;
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "null") || { vote: value };
      if (saved.vote !== value) throw new Error("Finish the pending vote before choosing another.");
      sessionStorage.setItem(key, JSON.stringify(saved));
      await publishApprovedPlan({
        load: async (pending?: PendingFunding) => { const result = await request<FundingStep & { confirmed: boolean }>(`/submissions/${submissionId}/reputation`, token, { vote: saved.vote, ...pending }); return { ...result, funded: result.confirmed }; },
        send: sendWalletTransaction, read: () => saved.pending,
        save: pending => { saved.pending = pending; sessionStorage.setItem(key, JSON.stringify(saved)); },
        changed: () => {}, wait: () => new Promise(resolve => window.setTimeout(resolve, 2500)), signal: active.signal,
      });
      sessionStorage.removeItem(key); if (!active.signal.aborted) await load();
    } catch (err) { if (!active.signal.aborted) setError(err instanceof Error ? err.message : "Vote is unverified. The saved transaction is retained."); }
    finally { running.current = false; if (!active.signal.aborted) setBusy(false); }
  }
  return <div className="notice" aria-label="Counterparty reputation">
    {rating?.supported ? <>
      <p><strong>{rating.role} reputation</strong>: {rating.up} up / {rating.down} down</p>
      <p className="muted">{rating.target?.slice(0, 8)}… · {rating.notice}</p>
      <a href={`https://explorer.testnet.arc.io/address/${rating.escrow}`} target="_blank" rel="noreferrer">View reputation contract</a>
      {rating.vote ? <p>Your permanent vote: {rating.vote === 1 ? "Up" : "Down"}</p> : rating.eligible ? <>
        <p>Your vote is public and permanent. Wallet confirmation uses testnet gas.</p>
        <button disabled={busy} onClick={() => void vote(1)}>Vote up</button>{" "}<button disabled={busy} onClick={() => void vote(-1)}>Vote down</button>
      </> : <p>Voting unlocks after payment.</p>}
    </> : rating && <p>{rating.notice}</p>}
    {busy && <p role="status">Confirm or reconcile your vote in the wallet…</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
