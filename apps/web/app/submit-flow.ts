import { request, sendWalletTransaction } from "./api";
import { publishApprovedPlan, type FundingStep } from "./publishing";

/** Continue the contributor's already-approved upload through its one exact
 * wallet authorization. Reuse the same receipt coordinator and recovery key as
 * manual recovery, so navigation/retries never blindly sign a second hash. */
export async function confirmUploadedSubmission(token: string, reservationId: string, signal: AbortSignal) {
  const key = `framebounty:action:${reservationId}:submit`;
  await publishApprovedPlan({
    signal,
    load: async pending => {
      const step = await request<FundingStep & { confirmed: boolean }>(`/reservations/${reservationId}/chain`, token,
        { purpose: "submit", confirmed: true, ...pending });
      return { ...step, funded: step.confirmed };
    },
    send: sendWalletTransaction,
    read: () => { const saved = sessionStorage.getItem(key); return saved ? JSON.parse(saved) : undefined; },
    save: pending => { if (pending) sessionStorage.setItem(key, JSON.stringify(pending)); else sessionStorage.removeItem(key); },
    changed: () => {},
    wait: () => new Promise(resolve => window.setTimeout(resolve, 2000)),
  });
}
