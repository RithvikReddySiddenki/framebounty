"use client";
import { moneyUnit, networkName, explorerUrl } from "./api";
import { useEffect, useState } from "react";
import { request, usdc } from "./api";
import Upload, { type Submission } from "./upload";
import WorkChat from "./work-chat";
import WalletAction from "./wallet-action";
import { ITEM_STEPS, Icon, Lifecycle, itemProgress } from "./ui";

type Reservation = {
  media_type: "image" | "video";
  fixture: boolean;
  id: string;
  task_id: string;
  state: string;
  reward_atomic: string;
  expires_at: string;
  rights_declaration: string;
  submission_id: string | null;
};

export default function Contributor({
  token,
  section = "tasks",
  onWorkReady,
}: {
  token?: string;
  section?: "tasks" | "submissions";
  onWorkReady?: () => void;
}) {
  const [reservations, setReservations] = useState<Reservation[]>([]);
  // Latest known submission per reservation, reported by each Upload box.
  const [submissions, setSubmissions] = useState<Record<string, Pick<Submission, "state" | "payment_confirmed">>>({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshMine() {
    if (!token) return;
    const data = await request<{ reservations: Reservation[] }>("/me/reservations", token);
    setReservations(data.reservations);
  }
  useEffect(() => {
    if (section === "submissions" && token) void run(refreshMine);
  }, [section, token]);
  useEffect(() => {
    const pending = reservations.filter(item => item.state === "reserve_pending");
    if (!token || section !== "submissions" || !pending.length) return;
    let checking = false;
    const timer = window.setInterval(() => {
      if (checking) return;
      checking = true;
      void (async () => {
        try {
          for (const item of pending) await request(`/reservations/${item.id}/sync`, token, {});
          await refreshMine();
        } catch (err) { setError(err instanceof Error ? err.message : "Could not check reservation confirmation"); }
        finally { checking = false; }
      })();
    }, 3000);
    return () => window.clearInterval(timer);
  }, [token, section, reservations]);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please retry.");
    } finally {
      setBusy(false);
    }
  }
  const earned = reservations.filter(r => {
    const s = submissions[r.id];
    return s?.payment_confirmed || ["fixture_accepted", "accepted", "paid"].includes(s?.state || r.state);
  }).reduce((sum, r) => sum + BigInt(r.reward_atomic), 0n);
  const anyFixture = reservations.some(r => r.fixture);

  return (
    <section className="panel contributor">
      <div hidden={section !== "tasks"}>
        <div className="page-heading">
          <div>
            <p className="eyebrow">Contributor workspace</p>
            <h1>Find work that fits.</h1>
            <p>Every task shown is already funded in escrow. Reserve one, capture it, upload, and get paid when AI verification passes.</p>
          </div>
        </div>
        <div className="panel">
          {token && <WorkChat token={token} onReserved={async () => { await refreshMine(); onWorkReady?.(); }} />}
        </div>
      </div>
      {token && (
        <section className="mine" hidden={section !== "submissions"}>
          <div className="page-heading">
            <div>
              <p className="eyebrow">Contributor workspace</p>
              <h1>Your submissions and rewards.</h1>
              <p className="intro">Follow your work from reservation through automatic verification. Pending rewards are not confirmed payments.</p>
            </div>
            <button disabled={busy} onClick={() => void run(refreshMine)}>Refresh my work</button>
          </div>
          {reservations.length > 0 && <div className="stat-row" style={{ margin: 0 }}>
            <div className="stat"><span>Reservations</span><strong>{reservations.length}</strong></div>
            <div className="stat"><span>{anyFixture ? "Released (simulated)" : "Paid"}</span><strong>{usdc(earned.toString())}<small>USDC</small></strong></div>
            <div className="stat"><span>Locked for you</span><strong>{usdc(reservations.reduce((sum, r) => sum + BigInt(r.reward_atomic), 0n) - earned + "")}<small>USDC</small></strong></div>
          </div>}
          <h2 hidden>Your reservations</h2>
          {!busy && reservations.length === 0 && <div className="empty"><Icon name="search" /><p>No reservations yet. Ask your work agent to find a funded task.</p></div>}
          {reservations.map((r) => {
            const submission = submissions[r.id];
            return <article className="panel" key={r.id}>
              <div className="reservation-summary">
                <div>
                  <p className="eyebrow">Reservation <span className="mono">{r.id.slice(0, 8)}</span> · {r.media_type}</p>
                  <h3 className="status-tag">{r.state.replaceAll("_", " ")}</h3>
                </div>
                <div className="task-reward">
                  {usdc(r.reward_atomic)}
                  <small>{moneyUnit(r.fixture)} fixed reward</small>
                </div>
              </div>
              <Lifecycle steps={ITEM_STEPS} progress={itemProgress(r.state, submission?.state ?? (r.submission_id ? "submitted" : null), submission?.payment_confirmed)} label={`Lifecycle for reservation ${r.id.slice(0, 8)}`} />
              <details className="reservation-details">
                <summary>Reservation details</summary>
                <p>Task {r.task_id}</p>
                <p>Upload deadline: {new Date(r.expires_at).toLocaleString()}</p>
              </details>
              {!r.fixture && r.state === "reserve_pending" && (
                <button disabled={busy} onClick={() => void run(async () => {
                  await request(`/reservations/${r.id}/sync`, token, {});
                  await refreshMine();
                })}>Check chain reservation</button>
              )}
              {!r.fixture && ["reserved", "submitted"].includes(r.state) && (
                <WalletAction token={token} reservationId={r.id} purpose="release"
                  label="Release only after the upload or review deadline expires" refreshed={refreshMine} />
              )}
              <Upload
                mediaType={r.media_type}
                reservationId={r.id}
                token={token}
                rights={r.rights_declaration}
                existingId={r.submission_id}
                canUpload={["fixture_reserved", "reserved"].includes(r.state)}
                onChanged={refreshMine}
                onSubmission={s => setSubmissions(current => ({ ...current, [r.id]: { state: s.state, payment_confirmed: s.payment_confirmed } }))}
              />
            </article>;
          })}
        </section>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
