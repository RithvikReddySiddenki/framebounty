"use client";
import { useEffect, useState } from "react";
import { request, sendFundingTransaction, usdc } from "./api";

type Step = {
  funded: boolean;
  state: string;
  step?: string;
  intent_id?: string;
  tx_hash?: string;
  amount_atomic?: string;
  last_error?: string;
  transaction?: {
    from: string;
    to: string;
    data: string;
    value: string;
    chainId: string;
  };
};

export default function Funding({
  token,
  jobId,
  planHash,
  onPublished,
  termsApproved = false,
}: {
  token: string;
  jobId: string;
  planHash: string;
  onPublished?: () => Promise<void>;
  termsApproved?: boolean;
}) {
  const [confirmed, setConfirmed] = useState(termsApproved);
  const [step, setStep] = useState<Step>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [recoveryHash, setRecoveryHash] = useState("");
  // Only public transaction metadata is stored, never auth tokens or signatures.
  const storageKey = `framebounty:funding:${jobId}`;
  async function update(send: boolean) {
    if (!confirmed || busy) return;
    setBusy(true);
    setError("");
    try {
      let pending: { intent_id: string; tx_hash: string } | undefined;
      const stored = sessionStorage.getItem(storageKey);
      if (stored) pending = JSON.parse(stored);
      if (recoveryHash && step?.intent_id) {
        if (!/^0x[0-9a-fA-F]{64}$/.test(recoveryHash))
          throw new Error(
            "Enter a complete transaction hash from wallet activity.",
          );
        pending = { intent_id: step.intent_id, tx_hash: recoveryHash };
      }
      // The single continue action reconciles an existing/recovered hash first.
      // An API timeout must never make this button request a second wallet send.
      if (send && !pending) {
        if (!step?.transaction || !step.intent_id || step.state !== "intent")
          throw new Error("Check the funding step first.");
        const tx_hash = await sendFundingTransaction(step.transaction);
        pending = { intent_id: step.intent_id, tx_hash };
        // Persist the hash before the API request: an API timeout must not cause
        // another wallet send. Rechecking submits the same identity and hash.
        sessionStorage.setItem(storageKey, JSON.stringify(pending));
      }
      const next = await request<Step>(`/jobs/${jobId}/funding`, token, {
        plan_hash: planHash,
        confirmed: true,
        ...pending,
      });
      setStep(next);
      if (next.funded) await onPublished?.();
      if (pending && (next.funded || next.intent_id !== pending.intent_id)) {
        sessionStorage.removeItem(storageKey);
        setRecoveryHash("");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not verify funding. Check wallet activity before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  // Reconcile only an already-broadcast transaction. Never request wallet
  // signatures automatically or send a replacement while a receipt is pending.
  useEffect(() => {
    if (!confirmed || !step?.tx_hash || step.funded || ["reverted", "invalid"].includes(step.state)) return;
    const timer = window.setInterval(() => void update(false), 4000);
    return () => window.clearInterval(timer);
  }, [confirmed, step, busy]);
  const stepLabel = step?.step === "create_job" ? "Create collection in wallet"
    : step?.step === "token_approve" ? "Approve exact budget in wallet"
    : step?.step === "deposit" ? "Deposit budget & publish" : "Prepare publishing";
  return (
    <section aria-label="Arc testnet funding">
      <h3>{step?.funded ? "Published" : "Publish your post"}</h3>
      <p>
        Wallet approval is required for each step: create escrow job, allow the
        exact test-USDC budget, then deposit. Native gas is separate. Listings
        appear only after verified funding. Contributors wait for confirmed
        reservations; payouts require human review and a separate wallet
        transaction.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
        />
        I confirm the saved plan and its fixed test-USDC budget.
      </label>
      {step?.funded ? (
        <p role="status">
          Open for contributors. Funding verified and initial tasks published.
        </p>
      ) : (
        <>
          {step && (
            <p role="status">
              {step.state === "intent" ? stepLabel : "Waiting for confirmed funding"}. Budget:{" "}
              {usdc(step.amount_atomic || "0")} test USDC.{" "}
              {step.tx_hash && `Transaction: ${step.tx_hash}`}
            </p>
          )}
          <button
            disabled={!confirmed || busy}
            className="primary"
            onClick={() => void update(step?.state === "intent")}
          >
            {busy ? "Checking…" : step?.state === "intent" ? stepLabel : step?.tx_hash ? "Check transaction status" : "Continue to publish"}
          </button>
          <details>
            <summary>Recover a wallet transaction</summary>
            <p>
              If the browser lost the wallet response, copy its hash from wallet
              activity and check it here before sending again.
            </p>
            <label>
              Existing transaction hash
              <input
                value={recoveryHash}
                onChange={(e) => setRecoveryHash(e.target.value)}
                placeholder="0x…"
              />
            </label>
          </details>
          {step?.last_error && <p role="status">{step.last_error}</p>}
        </>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
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
