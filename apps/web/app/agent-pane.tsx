"use client";

import { useState } from "react";
import { request, usdc } from "./api";

export type PlanProposal = {
  version: number;
  title: string;
  total: number;
  budget_atomic: string;
  reward_atomic: string;
  min_seconds: number;
  max_seconds: number;
  review_hours: number;
  rights_declaration: string;
  requirements: { key: string; description: string; minimum: number }[];
};
type Task = {
  task_id: string;
  title: string;
  version: number;
  reward_atomic: string;
  fixture: boolean;
  explanation: string;
  deadline: string;
  review_hours: number;
  reviewer: string;
  requirements: { key: string; description: string }[];
  tags: string[];
  rights_declaration: string;
};
type Pending = {
  confirmation_id: string;
  task_id: string;
  version: number;
  reward_atomic: string;
  expires_at: string;
  task: Task;
  requestId: string;
};
type ToolResult = {
  turn_id: string;
  tool: string;
  reply: string;
  provider_mode: string;
  data: {
    fixture?: boolean;
    tasks?: Task[];
    plan?: PlanProposal;
    reservations?: {
      id: string;
      task_id: string;
      state: string;
      reward_atomic: string;
    }[];
    coverage?: { accepted_total: number; pending_total: number };
    available_atomic?: string;
    published_slots?: number;
    explanation?: string;
  };
};
type Entry = {
  id: string;
  request_id: string;
  arguments: Record<string, unknown>;
  message: string | null;
  tool: string;
  state: string;
  result: ToolResult & { error?: string };
};
type Session = {
  id: string;
  role: "buyer" | "contributor";
  job_id: string | null;
  profile: { equipment?: string[]; available_minutes?: number };
};

export default function AgentPane({
  role,
  token,
  jobId,
  equipment = "phone,towel,dark_table",
  minutes = 20,
  onPlan,
  onReserved,
}: {
  role: "buyer" | "contributor";
  token?: string;
  jobId?: string;
  equipment?: string;
  minutes?: number;
  onPlan?: (plan: PlanProposal) => void;
  onReserved?: () => Promise<void>;
}) {
  const [scope, setScope] = useState<Session>();
  const [previous, setPrevious] = useState<Session[]>([]);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [message, setMessage] = useState(
    role === "buyer"
      ? jobId
        ? "Inspect my coverage"
        : "Plan 20 towel-folding videos with large towels and dark surfaces under 20 USDC"
      : "Find tasks I can do at home in 20 minutes.",
  );
  const [pending, setPending] = useState<Pending>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState<{ id: string; message: string }>();

  async function ensureSession(): Promise<Session> {
    if (!token)
      throw new Error("Connect and sign in to start a private conversation.");
    if (scope) return scope;
    const body =
      role === "buyer"
        ? { role, job_id: jobId || null }
        : {
            role,
            profile: {
              equipment: equipment
                .toLowerCase()
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
              available_minutes: minutes,
              preferences: "",
            },
          };
    const created = await request<Session>("/agent-sessions", token, body);
    setScope(created);
    return created;
  }
  async function loadHistory(id: string) {
    const data = await request<Session & { turns: Entry[] }>(
      `/agent-sessions/${id}`,
      token,
    );
    setScope(data);
    setEntries(data.turns);
    setPending(undefined);
  }
  async function send() {
    setBusy(true);
    setError("");
    const attempt =
      retry?.message === message ? retry : { id: crypto.randomUUID(), message };
    setRetry(attempt);
    try {
      const current = await ensureSession();
      await request<ToolResult>(
        `/agent-sessions/${current.id}/messages`,
        token,
        { message, request_id: attempt.id },
      );
      await loadHistory(current.id);
      setRetry(undefined);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Agent request failed");
    } finally {
      setBusy(false);
    }
  }
  async function prepare(task: Task) {
    if (!scope) return;
    setBusy(true);
    setError("");
    try {
      const result = await request<{ data: Omit<Pending, "requestId"> }>(
        `/agent-sessions/${scope.id}/tools`,
        token,
        {
          tool: "prepare_confirmation",
          arguments: { task_id: task.task_id },
          request_id: crypto.randomUUID(),
        },
      );
      setPending({ ...result.data, requestId: crypto.randomUUID() });
      const saved = await request<{ turns: Entry[] }>(
        `/agent-sessions/${scope.id}`,
        token,
      );
      setEntries(saved.turns);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Task changed; search again.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function reserveConfirmed() {
    if (!scope || !pending) return;
    setBusy(true);
    setError("");
    try {
      await request(`/agent-sessions/${scope.id}/tools`, token, {
        tool: "reserve_task",
        request_id: pending.requestId,
        arguments: {
          confirmation_id: pending.confirmation_id,
          task_id: pending.task_id,
          version: pending.version,
          reward_atomic: pending.reward_atomic,
          confirmed: true,
        },
      });
      setPending(undefined);
      await loadHistory(scope.id);
      await onReserved?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Reservation failed; refresh matching work.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function loadPrevious() {
    setBusy(true);
    setError("");
    try {
      const data = await request<{ sessions: Session[] }>(
        "/agent-sessions",
        token,
      );
      setPrevious(
        data.sessions.filter(
          (item) =>
            item.role === role && (item.job_id || null) === (jobId || null),
        ),
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load conversations",
      );
    } finally {
      setBusy(false);
    }
  }
  async function resumePending(entry: Entry) {
    if (!scope) return;
    setBusy(true);
    setError("");
    try {
      if (entry.message !== null) {
        await request(`/agent-sessions/${scope.id}/messages`, token, {
          message: entry.message,
          request_id: entry.request_id,
        });
      } else {
        await request(`/agent-sessions/${scope.id}/tools`, token, {
          tool: entry.tool,
          arguments: entry.arguments,
          request_id: entry.request_id,
        });
      }
      await loadHistory(scope.id);
      if (entry.tool === "reserve_task") await onReserved?.();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not resume the original action",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="agent-pane" aria-label={`${role} agent conversation`}>
      <p className="eyebrow">
        {role.toUpperCase()} AGENT · PRIVATE CONVERSATION
      </p>
      <p className="muted">
        Fixture mode uses deterministic responses and actual database records.
        Live mode requires configured Gemini access; it never silently falls
        back. Neither agent can approve quality or move arbitrary funds.
      </p>
      {role === "contributor" && (
        <p className="notice">
          Confirmed profile:{" "}
          {(scope?.profile.equipment || equipment.split(",")).join(", ")} ·{" "}
          {scope?.profile.available_minutes || minutes} minutes. Messages cannot
          add undeclared equipment. Change the form and start a new conversation
          to update it.
        </p>
      )}
      {token && (
        <>
          <button disabled={busy} onClick={() => void loadPrevious()}>
            Load saved {role} conversations
          </button>
          <button
            disabled={busy}
            onClick={() => {
              setScope(undefined);
              setEntries([]);
              setPending(undefined);
              setRetry(undefined);
              setError("");
            }}
          >
            Start new {role} conversation
          </button>
        </>
      )}
      {previous.map((item, index) => (
        <button
          key={item.id}
          disabled={busy}
          onClick={() => {
            void loadHistory(item.id).catch((err) => setError(err.message));
          }}
        >
          Resume conversation {index + 1}
        </button>
      ))}
      <div className="conversation-log" aria-live="polite">
        {entries.map((entry) => (
          <article key={entry.id} className="conversation-entry">
            {entry.message && (
              <p>
                <strong>You:</strong> {entry.message}
              </p>
            )}
            {entry.state === "failed" ? (
              <p className="error">
                {entry.result.error} Submit a new message after resolving the
                issue.
              </p>
            ) : entry.state !== "completed" ? (
              <div>
                <p>
                  Action pending. Resume the original saved intention without
                  creating a second action.
                </p>
                <button
                  disabled={busy}
                  onClick={() => void resumePending(entry)}
                >
                  Resume saved action
                </button>
              </div>
            ) : (
              <>
                <p>
                  <strong>
                    {role === "buyer" ? "Buyer" : "Contributor"} agent:
                  </strong>{" "}
                  {entry.result.reply}
                </p>
                <p className="muted">
                  {entry.result.provider_mode === "fixture"
                    ? "Deterministic fixture response"
                    : "Validated Gemini proposal"}{" "}
                  · Action: {entry.tool.replaceAll("_", " ")}
                </p>
                {entry.result.data.plan && (
                  <div className="notice">
                    <p>
                      {entry.result.data.plan.title}:{" "}
                      {entry.result.data.plan.total} clips,{" "}
                      {usdc(String(entry.result.data.plan.reward_atomic))} USDC
                      per clip, {entry.result.data.plan.review_hours}-hour human
                      review.
                    </p>
                    <p>
                      This is a draft proposal, not a confirmed or funded job.
                    </p>
                    {onPlan && (
                      <button onClick={() => onPlan(entry.result.data.plan!)}>
                        Review proposed plan in editor
                      </button>
                    )}
                  </div>
                )}
                {entry.result.data.coverage && (
                  <p>
                    {entry.result.data.coverage.accepted_total} accepted clips ·{" "}
                    {entry.result.data.coverage.pending_total} active promises ·
                    available {usdc(entry.result.data.available_atomic || "0")}{" "}
                    {entry.result.provider_mode === "fixture"
                      ? "simulated"
                      : "test"}{" "}
                    USDC.
                  </p>
                )}
                {entry.result.data.published_slots !== undefined && (
                  <p>
                    {entry.result.data.published_slots}{" "}
                    {entry.result.data.fixture ? "fixture" : "testnet"} slots
                    published. {entry.result.data.explanation}
                  </p>
                )}
                {entry.result.data.tasks?.length === 0 && (
                  <p>
                    No matching funded work. Try a different confirmed profile
                    or return later.
                  </p>
                )}
                {entry.result.data.tasks?.map((task) => (
                  <div key={task.task_id} className="agent-task">
                    <h3>{task.title}</h3>
                    <p>
                      {usdc(task.reward_atomic)}{" "}
                      {task.fixture ? "fixture" : "test"} USDC · task version{" "}
                      {task.version}
                    </p>
                    <p>{task.explanation}</p>
                    <p className="muted">
                      Task {task.task_id} · upload before{" "}
                      {new Date(task.deadline).toLocaleString()} ·{" "}
                      {task.review_hours}-hour review window.
                    </p>
                    <details>
                      <summary>Rubric, usage rights & review terms</summary>
                      {task.requirements
                        .filter((rule) => task.tags.includes(rule.key))
                        .map((rule) => (
                          <p key={rule.key}>{rule.description}</p>
                        ))}
                      <p>{task.rights_declaration}</p>
                      <p>
                        Full task completion requires human approval. Reviewer:{" "}
                        {task.reviewer}. An abandoned review releases funds
                        after timeout rather than automatically paying.
                      </p>
                    </details>
                    <button disabled={busy} onClick={() => void prepare(task)}>
                      Review agent reservation terms
                    </button>
                  </div>
                ))}
                {entry.result.data.reservations?.map((item) => (
                  <p key={item.id}>
                    {item.task_id}: {item.state.replaceAll("_", " ")} ·{" "}
                    {usdc(item.reward_atomic)} USDC
                  </p>
                ))}
              </>
            )}
          </article>
        ))}
      </div>
      {pending && (
        <div
          className="confirmation"
          role="region"
          aria-label="Agent task confirmation"
        >
          <strong>Confirm this specific task and reward</strong>
          <p>
            {pending.task.title} · {usdc(pending.reward_atomic)}{" "}
            {pending.task.fixture ? "fixture" : "test"} USDC · version{" "}
            {pending.version}
          </p>
          <p>
            Task {pending.task_id}. Confirmation expires at{" "}
            {new Date(pending.expires_at).toLocaleTimeString()}. Your
            authenticated wallet is the recipient.
          </p>
          <button
            className="primary"
            disabled={busy}
            onClick={() => void reserveConfirmed()}
          >
            Confirm agent task & reward
          </button>
          <button disabled={busy} onClick={() => setPending(undefined)}>
            Cancel agent confirmation
          </button>
        </div>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <label htmlFor={`${role}-message-${jobId || "general"}`}>
          {role === "buyer" ? "Buyer" : "Contributor"} message
        </label>
        <textarea
          id={`${role}-message-${jobId || "general"}`}
          rows={3}
          maxLength={4000}
          value={message}
          onChange={(event) => {
            setMessage(event.target.value);
            setRetry(undefined);
          }}
          disabled={busy}
        />
        <button
          className="primary"
          disabled={!token || busy || !message.trim()}
        >
          {busy ? "Working…" : `Send ${role} message`}
        </button>
      </form>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
