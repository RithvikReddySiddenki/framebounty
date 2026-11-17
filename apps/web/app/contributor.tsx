"use client";
import { useState } from "react";
import { request, usdc } from "./api";
import Upload from "./upload";
import AgentPane from "./agent-pane";
import WalletAction from "./wallet-action";

type Task = {
  task_id: string;
  title: string;
  version: number;
  reward_atomic: string;
  equipment: string[];
  tags: string[];
  minutes: number;
  deadline: string;
  fixture: boolean;
  review_hours: number;
  reviewer: string;
  explanation: string;
  requirements: { key: string; description: string }[];
  min_seconds: number;
  max_seconds: number;
  rubric_hash: string;
  rights_declaration: string;
};
type Confirmation = {
  confirmation_id: string;
  task_id: string;
  version: number;
  reward_atomic: string;
  expires_at: string;
};
type Reservation = {
  fixture: boolean;
  id: string;
  task_id: string;
  state: string;
  reward_atomic: string;
  expires_at: string;
  rights_declaration: string;
  submission_id: string | null;
};

export default function Contributor({ token }: { token?: string }) {
  const [equipment, setEquipment] = useState("phone,towel,dark_table");
  const [minutes, setMinutes] = useState(20);
  const [tasks, setTasks] = useState<Task[] | null>(null);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  const [retryKey, setRetryKey] = useState("");

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
  async function search() {
    const result = await request<{ tasks: Task[] }>(
      `/tasks?equipment=${encodeURIComponent(equipment)}&minutes=${minutes}`,
    );
    setTasks(result.tasks);
    setConfirmation(null);
  }
  async function prepare(task: Task) {
    if (!token) throw new Error("Connect and sign in before reserving a task.");
    const result = await request<Confirmation>(
      `/tasks/${task.task_id}/confirmation`,
      token,
      {},
    );
    if (
      result.version !== task.version ||
      result.reward_atomic !== task.reward_atomic
    ) {
      await search();
      throw new Error("Task terms changed. Review the updated listing.");
    }
    setConfirmation(result);
    setRetryKey(crypto.randomUUID());
  }
  async function confirm() {
    if (!confirmation || !token) return;
    const result = await request<{ id: string; state: string }>(
      "/reservations",
      token,
      {
        confirmation_id: confirmation.confirmation_id,
        task_id: confirmation.task_id,
        version: confirmation.version,
        reward_atomic: confirmation.reward_atomic,
        idempotency_key: retryKey,
        confirmed: true,
      },
    );
    setStatus(
      `Reservation ${result.id}: ${result.state.replaceAll("_", " ")}. ${result.state.startsWith("fixture_") ? "Fixture rewards have no monetary value." : "Wait for chain confirmation before collecting or uploading."}`,
    );
    const mine = await request<{ reservations: Reservation[] }>(
      "/me/reservations",
      token,
    );
    setReservations(mine.reservations);
    setConfirmation(null);
    await search();
  }
  return (
    <section className="panel contributor">
      <p className="eyebrow">CONTRIBUTOR WORKSPACE</p>
      <h1>
        Good work starts
        <br />
        with a good fit.
      </h1>
      <p className="intro">
        Search published records using your declared equipment and availability.
        Every result explains its requirements.
      </p>
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          void run(search);
        }}
      >
        <div>
          <label htmlFor="equipment">Equipment (comma-separated)</label>
          <input
            id="equipment"
            value={equipment}
            onChange={(e) => setEquipment(e.target.value)}
            maxLength={500}
          />
        </div>
        <div>
          <label htmlFor="minutes">Available minutes</label>
          <input
            id="minutes"
            type="number"
            min={1}
            max={1440}
            value={minutes}
            onChange={(e) => setMinutes(Number(e.target.value))}
          />
        </div>
        <button className="primary" disabled={busy}>
          {busy ? "Working…" : "Find matching tasks ↗"}
        </button>
      </form>
      <AgentPane
        role="contributor"
        token={token}
        equipment={equipment}
        minutes={minutes}
        onReserved={async () => {
          const data = await request<{ reservations: Reservation[] }>(
            "/me/reservations",
            token,
          );
          setReservations(data.reservations);
        }}
      />
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {status && (
        <p className="notice" role="status">
          {status}
        </p>
      )}
      {tasks === null ? (
        <div className="empty">
          <h2>Start with what you have</h2>
          <p>
            Tell us your equipment and time. No match is a valid result;
            available tasks depend on confirmed funding and remaining slots.
          </p>
        </div>
      ) : tasks.length === 0 ? (
        <div className="empty">
          <h2>No matching work right now</h2>
          <p>
            Try different equipment or check back later. No reservation or
            earning is implied.
          </p>
        </div>
      ) : (
        <div className="task-grid">
          {tasks.map((task) => (
            <article className="panel" key={task.task_id}>
              <p className="eyebrow">
                {task.fixture ? "SIMULATED FUNDS · FIXTURE" : "FUNDED LISTING"}
              </p>
              <h2>{task.title}</h2>
              <p>
                {usdc(task.reward_atomic)}{" "}
                {task.fixture ? "fixture USDC" : "test USDC"} · {task.minutes}{" "}
                minutes
              </p>
              <p className="muted">{task.explanation}</p>
              <p className="muted">
                Task {task.task_id} · Version {task.version}
                <br />
                Upload before {new Date(task.deadline).toLocaleString()}
                <br />
                Review window: {task.review_hours} hours
              </p>
              <p className="muted">
                Requires a complete towel-folding demonstration. A reviewer must
                approve payment. Rejection or abandoned review can release the
                reward after timeout.
              </p>
              <button
                disabled={busy}
                onClick={() => void run(() => prepare(task))}
              >
                Review reservation terms
              </button>
              <details>
                <summary>Immutable rubric & usage rights</summary>
                <p>
                  {task.min_seconds}–{task.max_seconds} seconds. Complete towel
                  fold required.
                </p>
                {task.requirements
                  .filter((r) => task.tags.includes(r.key))
                  .map((r) => (
                    <p key={r.key}>{r.description}</p>
                  ))}
                <p>{task.rights_declaration}</p>
                <p className="muted">
                  Reviewer: {task.reviewer}
                  <br />
                  Rubric: {task.rubric_hash}
                </p>
              </details>
              {confirmation?.task_id === task.task_id && (
                <div className="confirmation">
                  <strong>Confirm this specific task</strong>
                  <p>
                    {usdc(confirmation.reward_atomic)}{" "}
                    {task.fixture ? "fixture USDC" : "test USDC"}, task version{" "}
                    {confirmation.version}. Confirm before{" "}
                    {new Date(confirmation.expires_at).toLocaleTimeString()}.
                  </p>
                  <button
                    className="primary"
                    disabled={busy}
                    onClick={() => void run(confirm)}
                  >
                    Confirm & reserve
                  </button>
                  <button disabled={busy} onClick={() => setConfirmation(null)}>
                    Cancel
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
      {token && (
        <section className="mine">
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
              <p>
                {r.task_id} · {r.state.replaceAll("_", " ")} ·{" "}
                {usdc(r.reward_atomic)}{" "}
                {r.fixture ? "fixture USDC" : "test USDC"}
              </p>
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
                reservationId={r.id}
                token={token}
                rights={r.rights_declaration}
                existingId={r.submission_id}
                canUpload={["fixture_reserved", "reserved"].includes(r.state)}
              />
            </article>
          ))}
        </section>
      )}
    </section>
  );
}
