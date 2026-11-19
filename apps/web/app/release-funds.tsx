"use client";
import { useEffect, useRef, useState } from "react";
import { request, sendWalletTransaction, usdc } from "./api";
import { publishApprovedPlan, type FundingStep, type PendingFunding } from "./publishing";

/** The sole buyer quality-flow action: authorize payment of verified work. */
export default function ReleaseFunds({ token, jobId, count, pending, fixture, amountAtomic, onChanged }: {
  token: string; jobId: string; count: number; pending: boolean; fixture: boolean; amountAtomic: string; onChanged: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const controller = useRef<AbortController | undefined>(undefined);
  const running = useRef(false);
  const key = `framebounty:release:${jobId}`;
  useEffect(() => () => controller.current?.abort(), []);
  async function release() {
    if (running.current) return;
    running.current = true; setBusy(true); setError("");
    const active = new AbortController(); controller.current = active;
    try {
      const stored = sessionStorage.getItem(key);
      const saved = stored ? JSON.parse(stored) : { request_id: crypto.randomUUID() };
      sessionStorage.setItem(key, JSON.stringify(saved));
      await publishApprovedPlan({
        load: async (transaction?: PendingFunding) => {
          const result = await request<FundingStep & { confirmed: boolean; legacy?: boolean }>(`/jobs/${jobId}/release-funds`, token,
            { confirmed: true, request_id: saved.request_id, ...transaction });
          if (result.state === "reverted") {
            // A verified revert pays nobody. A subsequent explicit click may
            // create a fresh batch; unknown outcomes keep the saved identity.
            sessionStorage.removeItem(key);
          }
          if (result.legacy) setStatus("This collection uses the original escrow. Your wallet may request one approval per verified submission; its funds remain in that original contract.");
          return { ...result, funded: result.confirmed };
        },
        send: sendWalletTransaction,
        read: () => saved.pending,
        save: transaction => { saved.pending = transaction; sessionStorage.setItem(key, JSON.stringify(saved)); },
        changed: step => { if (!step.funded) setStatus("Release pending. Follow your wallet prompts; payment is recorded only after a successful receipt."); },
        wait: () => new Promise(resolve => window.setTimeout(resolve, 2500)), signal: active.signal,
      });
      sessionStorage.removeItem(key);
      if (!active.signal.aborted) { setStatus(fixture ? "Simulated funds released. No blockchain payment occurred." : "Funds released; successful payment receipt verified."); await onChanged(); }
    } catch (err) { if (!active.signal.aborted) setError(err instanceof Error ? err.message : "Release could not be verified; the saved transaction is retained."); }
    finally { running.current = false; if (!active.signal.aborted) setBusy(false); }
  }
  return <section className="notice" aria-label="Final funds release">
    <h3>{count} AI-verified submission{count === 1 ? "" : "s"} ready · {usdc(amountAtomic)} {fixture ? "simulated" : "test"} USDC</h3>
    <p>Verification is automatic. This action releases the fixed rewards early to their reserved contributors. Protected posts pay automatically one hour after on-chain verification if you take no action. Failed or uncertain submissions cannot enter this batch.</p>
    <button className="primary" disabled={busy || (!count && !pending)} onClick={() => void release()}>{busy ? "Releasing…" : pending ? "Continue funds release" : fixture ? "Release simulated funds" : "Release approved funds"}</button>
    {status && <p role="status">{status}</p>}{error && <p className="error" role="alert">{error}</p>}
  </section>;
}
