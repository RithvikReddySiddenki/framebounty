/** Advance only saved, receipt-gated server instructions for the approved plan.
 * Existing hashes are always reconciled before requesting another signature.
 * The caller's abort signal prevents subsequent prompts after sign-out/navigation.
 */
export type FundingStep = {
  funded: boolean; state: string; step?: string; intent_id?: string; tx_hash?: string;
  amount_atomic?: string; last_error?: string;
  transaction?: { from: string; to: string; data: string; value: string; chainId: string };
};
export type PendingFunding = { intent_id: string; tx_hash: string };
export async function publishApprovedPlan(options: {
  load: (pending?: PendingFunding) => Promise<FundingStep>;
  send: (transaction: NonNullable<FundingStep["transaction"]>) => Promise<string>;
  read: () => PendingFunding | undefined;
  save: (pending?: PendingFunding) => void;
  changed: (step: FundingStep) => void;
  wait: () => Promise<void>;
  signal: AbortSignal;
  maxChecks?: number;
}): Promise<void> {
  const check = () => { if (options.signal.aborted) throw new Error("Publishing stopped. Resume the saved post to check its transaction status."); };
  check();
  let pending = options.read();
  let step = await options.load(pending);
  for (let count = 0; count < (options.maxChecks ?? 90); count++) {
    check(); options.changed(step);
    if (step.funded) { options.save(undefined); return; }
    if (["reverted", "invalid"].includes(step.state)) throw new Error(step.last_error || "The transaction did not succeed. Check wallet activity before retrying.");
    if (pending && step.intent_id !== pending.intent_id) { options.save(undefined); pending = undefined; }
    if (step.state === "intent" && !pending) {
      if (!step.transaction || !step.intent_id) throw new Error("The server did not provide a complete publishing step.");
      check();
      const hash = await options.send(step.transaction);
      // Persist even if navigation happened while the wallet was open. The next
      // browser session must recover this hash rather than send another payment.
      pending = { intent_id: step.intent_id, tx_hash: hash };
      options.save(pending); check();
      step = await options.load(pending);
    } else if (pending || ["broadcast", "signed"].includes(step.state)) {
      await options.wait(); check(); step = await options.load(pending);
    } else {
      throw new Error("Publishing needs attention. Check the saved post and wallet activity before continuing.");
    }
  }
  throw new Error("Still waiting for confirmation. Your transaction is saved; continue publishing later without sending it again.");
}
