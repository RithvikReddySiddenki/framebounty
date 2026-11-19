"use client";
import { useEffect, useState } from "react";
import { request, usdc } from "./api";
import Upload from "./upload";
import WorkChat from "./work-chat";
import WalletAction from "./wallet-action";

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
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshMine() {
    if (!token) return;
    const data = await request<{ reservations: Reservation[] }>(
      "/me/reservations",
      token,
    );
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
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong. Please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel contributor">
      <div hidden={section !== "tasks"}>
        <p className="eyebrow">CONTRIBUTOR WORKSPACE</p>
        <h1>Find work that fits.</h1>
        {token && <WorkChat token={token} onReserved={async () => { await refreshMine(); onWorkReady?.(); }} />}
      </div>
      {token && (
        <section className="mine" hidden={section !== "submissions"}>
          <p className="eyebrow">CONTRIBUTOR WORKSPACE</p>
          <h1>Your submissions and rewards.</h1>
          <p className="intro">
            Follow your work from reservation through automatic verification. Pending
            rewards are not confirmed payments.
          </p>
          <h2>Your reservations</h2>
          <button
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const data = await request<{ reservations: Reservation[] }>(
                  "/me/reservations",
                  token,
                );
                setReservations(data.reservations);
              })
            }
          >
            Refresh my work
          </button>
          {reservations.map((r) => (
            <article className="panel" key={r.id}>
              <div className="reservation-summary">
                <div>
                  <p className="eyebrow">Reservation {r.id.slice(0, 8)}</p>
                  <h3 className="status-tag">{r.state.replaceAll("_", " ")}</h3>
                </div>
                <div className="task-reward">
                  {usdc(r.reward_atomic)}
                  <small>
                    {r.fixture ? "fixture USDC" : "test USDC"} fixed reward
                  </small>
                </div>
              </div>
              <details className="reservation-details">
                <summary>Reservation details</summary>
                <p>Task {r.task_id}</p>
                <p>
                  Upload deadline: {new Date(r.expires_at).toLocaleString()}
                </p>
              </details>
              {!r.fixture && r.state === "reserve_pending" && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await request(`/reservations/${r.id}/sync`, token, {});
                      const mine = await request<{
                        reservations: Reservation[];
                      }>("/me/reservations", token);
                      setReservations(mine.reservations);
                    })
                  }
                >
                  Check chain reservation
                </button>
              )}
              {!r.fixture && ["reserved", "submitted"].includes(r.state) && (
                <WalletAction
                  token={token}
                  reservationId={r.id}
                  purpose="release"
                  label="Release only after the upload or review deadline expires"
                  refreshed={async () => {
                    const mine = await request<{ reservations: Reservation[] }>(
                      "/me/reservations",
                      token,
                    );
                    setReservations(mine.reservations);
                  }}
                />
              )}
              <Upload
                mediaType={r.media_type}
                reservationId={r.id}
                token={token}
                rights={r.rights_declaration}
                existingId={r.submission_id}
                canUpload={["fixture_reserved", "reserved"].includes(r.state)}
                onChanged={refreshMine}
              />
            </article>
          ))}
        </section>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
