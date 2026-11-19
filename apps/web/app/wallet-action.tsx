"use client";
import { useState } from "react";
import { request, sendWalletTransaction } from "./api";

type Result = {
  intent_id: string;
  state: string;
  confirmed: boolean;
  reservation_state: string;
  tx_hash?: string;
  step: string;
  transaction: {
    from: string;
    to: string;
    data: string;
    value: string;
    chainId: string;
  };
};

export default function WalletAction({
  token,
  reservationId,
  purpose,
  label,
  refreshed,
}: {
  token: string;
  reservationId: string;
  purpose: "submit" | "review" | "release";
  label: string;
  refreshed: () => Promise<void>;
}) {
  const [result, setResult] = useState<Result>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [hash, setHash] = useState("");
  const key = `framebounty:action:${reservationId}:${purpose}`;
  async function act(send: boolean) {
    setBusy(true);
    setError("");
    try {
      const stored = sessionStorage.getItem(key);
      let existing: { intent_id: string; tx_hash: string } | undefined = stored
        ? JSON.parse(stored)
        : undefined;
      if (hash && result) {
        if (!/^0x[0-9a-fA-F]{64}$/.test(hash))
          throw new Error("Enter the complete existing transaction hash.");
        existing = { intent_id: result.intent_id, tx_hash: hash };
      }
      if (send) {
        if (!result || result.state !== "intent" || existing)
          throw new Error("Reconcile the existing transaction first.");
        const tx_hash = await sendWalletTransaction(result.transaction);
        existing = { intent_id: result.intent_id, tx_hash };
        sessionStorage.setItem(key, JSON.stringify(existing));
      }
      const next = await request<Result>(
        `/reservations/${reservationId}/chain`,
        token,
        { purpose, confirmed: true, ...existing },
      );
      setResult(next);
      if (next.confirmed) {
        sessionStorage.removeItem(key);
        setHash("");
        await refreshed();
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Chain outcome unverified. Check wallet activity before retrying.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={label}>
      <p>
        {label}. This requests a separate wallet transaction and uses native
        testnet gas.
      </p>
      <button disabled={busy} onClick={() => void act(false)}>
        Prepare / check {purpose} transaction
      </button>
      {result && (
        <p role="status">
          {result.step}: {result.state}. Reservation: {result.reservation_state}
          . {result.tx_hash}
        </p>
      )}
      {result?.state === "intent" && (
        <button disabled={busy} onClick={() => void act(true)}>
          Authorize {result.step} in wallet
        </button>
      )}
      {result && !result.confirmed && (
        <details>
          <summary>Recover an existing wallet transaction</summary>
          <label>
            Transaction hash from wallet activity
            <input value={hash} onChange={(e) => setHash(e.target.value)} />
          </label>
          <p>Check this hash before requesting another signature.</p>
        </details>
      )}
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </section>
  );
}
