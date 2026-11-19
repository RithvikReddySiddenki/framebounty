"use client";
import { useEffect, useRef, useState } from "react";
import { request, sendWalletTransaction } from "./api";
import { publishApprovedPlan, type FundingStep, type PendingFunding } from "./publishing";

export default function RefundUnused({ token, jobId, onChanged }: { token: string; jobId: string; onChanged: () => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const controller = useRef<AbortController | undefined>(undefined);
  const running = useRef(false);
  useEffect(() => () => controller.current?.abort(), []);
  async function refund() {
    if (running.current) return;
    running.current = true; setBusy(true); setMessage("");
    const active = new AbortController(); controller.current = active;
    const key = `framebounty:refund:${jobId}`;
    try {
      const saved = JSON.parse(sessionStorage.getItem(key) || "null") || { request_id: crypto.randomUUID() };
      sessionStorage.setItem(key, JSON.stringify(saved));
      await publishApprovedPlan({
        load: (pending?: PendingFunding) => request<FundingStep>(`/jobs/${jobId}/refund-unused`, token, { confirmed: true, request_id: saved.request_id, ...pending }),
        send: sendWalletTransaction, read: () => saved.pending,
        save: pending => { saved.pending = pending; sessionStorage.setItem(key, JSON.stringify(saved)); },
        changed: () => {}, wait: () => new Promise(resolve => window.setTimeout(resolve, 2500)), signal: active.signal,
      });
      sessionStorage.removeItem(key);
      if (!active.signal.aborted) { setMessage("Unused budget returned. Active contributor rewards remain protected."); await onChanged(); }
    } catch (err) { if (!active.signal.aborted) setMessage(err instanceof Error ? err.message : "Refund remains unverified; the existing transaction is retained."); }
    finally { running.current = false; if (!active.signal.aborted) setBusy(false); }
  }
  return <section className="notice"><p>The post has expired. Recover only unused budget; active reservations and submissions keep their rewards.</p><button disabled={busy} onClick={() => void refund()}>{busy ? "Confirm refund in wallet…" : "Refund unused budget"}</button>{message && <p role="status">{message}</p>}</section>;
}
