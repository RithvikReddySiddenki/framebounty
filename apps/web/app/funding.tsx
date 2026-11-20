"use client";
import { moneyUnit, networkName, explorerUrl } from "./api";
import { useEffect, useRef, useState } from "react";
import { request, sendFundingTransaction, usdc } from "./api";
import { publishApprovedPlan, type FundingStep, type PendingFunding } from "./publishing";

export default function Funding({ token, jobId, planHash, onPublished, termsApproved = false, autoStart = false }: {
  token: string; jobId: string; planHash: string; onPublished?: () => Promise<void>;
  termsApproved?: boolean; autoStart?: boolean;
}) {
  const [step, setStep] = useState<FundingStep>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recoveryHash, setRecoveryHash] = useState("");
  const running = useRef(false);
  const controller = useRef<AbortController | undefined>(undefined);
  const storageKey = `framebounty:funding:${jobId}`;
  useEffect(() => () => controller.current?.abort(), []);
  async function publish() {
    if (running.current) return;
    running.current = true; setBusy(true); setError("");
    const active = new AbortController(); controller.current = active;
    try {
      if (recoveryHash) {
        if (!/^0x[0-9a-fA-F]{64}$/.test(recoveryHash)) throw new Error("Enter a complete wallet transaction hash.");
        const current = step || await request<FundingStep>(`/jobs/${jobId}/funding`, token, { plan_hash: planHash, confirmed: true });
        if (!current.intent_id) throw new Error("No publishing transaction is awaiting recovery.");
        sessionStorage.setItem(storageKey, JSON.stringify({ intent_id: current.intent_id, tx_hash: recoveryHash }));
      }
      await publishApprovedPlan({
        load: pending => request<FundingStep>(`/jobs/${jobId}/funding`, token, { plan_hash: planHash, confirmed: true, ...pending }),
        send: sendFundingTransaction,
        read: () => { const stored = sessionStorage.getItem(storageKey); return stored ? JSON.parse(stored) as PendingFunding : undefined; },
        save: pending => { if (pending) sessionStorage.setItem(storageKey, JSON.stringify(pending)); else sessionStorage.removeItem(storageKey); },
        changed: setStep,
        wait: () => new Promise(resolve => window.setTimeout(resolve, 2500)), signal: active.signal,
      });
      if (!active.signal.aborted) { setRecoveryHash(""); await onPublished?.(); }
    } catch (err) { if (!active.signal.aborted) setError(err instanceof Error ? err.message : "Publishing failed; your saved post is preserved."); }
    finally { running.current = false; if (!active.signal.aborted) setBusy(false); }
  }
  useEffect(() => {
    if (!autoStart || !termsApproved) return;
    // Delay until after StrictMode's setup/cleanup probe to avoid duplicate starts.
    const timer = window.setTimeout(() => void publish(), 0);
    return () => window.clearTimeout(timer);
  }, [autoStart, termsApproved, jobId, token]);
  const label = (step?.step === "create_job" || step?.step === "create_protected") ? "Creating escrow" : step?.step === "token_approve" ? "Approving the exact budget" : "Depositing budget";
  return <section aria-label={`${networkName()} funding`}>
    <h3>{step?.funded ? "Open for contributors" : busy ? "Publishing your post" : "Publish your saved post"}</h3>
    <p>Publishing guides you through authorizing escrow creation, the exact allowance and the deposit. Approve each request in the secure authorization window.</p>
    {step && <p role="status">{step.funded ? "Funding verified. Your first tasks are now public." : `${label}${step.state === "intent" ? " - awaiting your authorization" : " - waiting for confirmation"}`}{step.amount_atomic && ` · ${usdc(step.amount_atomic)} ${moneyUnit()}`}</p>}
    {!step?.funded && (!autoStart || error) && <button className="primary" disabled={busy} onClick={() => void publish()}>{busy ? "Follow the authorization prompts" : autoStart ? "Resume publishing" : "Publish post"}</button>}
    {!step?.funded && <details><summary>Recover a wallet transaction</summary><p>Only if the wallet lost its response: enter the existing hash, then continue. Existing transactions are checked before any new signature.</p><label>Existing transaction hash<input value={recoveryHash} disabled={busy} onChange={e => setRecoveryHash(e.target.value)} placeholder="0x?" /></label></details>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}

export function ResumeFunding({ token }: { token: string }) {
  const [jobs, setJobs] = useState<
    { id: string; title: string; fixture: boolean; state: string }[]
  >([]);
  const [selected, setSelected] = useState<{ id: string; plan_hash: string }>();
  const [error, setError] = useState("");
  async function load(jobId?: string) {
    setError("");
    try {
      if (jobId)
        setSelected(
          await request<{ id: string; plan_hash: string }>(
            `/jobs/${jobId}`,
            token,
          ),
        );
      else {
        const result = await request<{ jobs: typeof jobs }>("/me/jobs", token);
        setJobs(
          result.jobs.filter(
            (job) => !job.fixture && ["draft", "open"].includes(job.state),
          ),
        );
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load saved jobs.",
      );
    }
  }
  return (
    <section className="buyer-edit">
      <h2>Resume saved testnet funding</h2>
      <button onClick={() => void load()}>Load my saved jobs</button>
      {jobs.map((job) => (
        <p key={job.id}>
          <button onClick={() => void load(job.id)}>
            {job.title} · {job.id.slice(0, 8)} · {job.state}
          </button>
        </p>
      ))}
      {selected && (
        <Funding
          key={selected.id}
          token={token}
          jobId={selected.id}
          planHash={selected.plan_hash}
        />
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
