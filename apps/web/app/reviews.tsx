"use client";

import { useEffect, useState } from "react";
import { apiBase, request } from "./api";
import MediaView from "./media-view";
import AgentPane from "./agent-pane";
import type { Submission } from "./upload";
import WalletAction from "./wallet-action";

type Job = { id: string; title: string; state: string; fixture: boolean };
type Coverage = {
  accepted_total: number;
  pending_total: number;
  accepted_categories: Record<string, number>;
  fixture: boolean;
};

function ReviewCard({
  item,
  token,
  refreshed,
}: {
  item: Submission;
  token: string;
  refreshed: () => Promise<void>;
}) {
  const [watched, setWatched] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [large, setLarge] = useState(false);
  const [dark, setDark] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mediaVisible, setMediaVisible] = useState(false);
  const reviewable = item.state === "needs_review" || item.state === "invalid";
  async function decide(decision: "accept" | "reject") {
    setBusy(true);
    setError("");
    try {
      await request(`/submissions/${item.id}/review`, token, {
        decision,
        task_completed: completed,
        watched_full_video: watched,
        tags:
          decision === "accept"
            ? [
                ...(large ? ["large_towel"] : []),
                ...(dark ? ["dark_surface"] : []),
              ]
            : [],
        reason,
      });
      await refreshed();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Review failed; please retry.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="panel review-card">
      <p className="eyebrow">
        {item.fixture ? "FIXTURE SUBMISSION" : "TESTNET SUBMISSION"} ·{" "}
        {item.state.replaceAll("_", " ")}
      </p>
      <h3>Submission {item.id.slice(0, 8)}</h3>
      {!item.fixture &&
        !["accepted", "rejected", "expired", "timed_out"].includes(
          item.state,
        ) && (
          <WalletAction
            token={token}
            reservationId={item.reservation_id}
            purpose="release"
            label="Release only after the applicable deadline expires"
            refreshed={refreshed}
          />
        )}
      {!item.fixture &&
        ["accept_pending", "reject_pending"].includes(item.state) && (
          <WalletAction
            token={token}
            reservationId={item.reservation_id}
            purpose="review"
            label={
              item.state === "accept_pending"
                ? "Pay the fixed recipient for this human-reviewed submission"
                : "Confirm this human review rejection on chain"
            }
            refreshed={refreshed}
          />
        )}
      <p className="muted">
        Review before {new Date(item.review_deadline).toLocaleString()}.{" "}
        {item.payment_confirmed
          ? "Chain payment confirmed."
          : "No chain payment confirmed."}
      </p>
      <button onClick={() => setMediaVisible(!mediaVisible)}>
        {mediaVisible
          ? "Hide private video & frames"
          : "Watch full video & inspect frames"}
      </button>
      {mediaVisible && (
        <>
          <MediaView path={`/submissions/${item.id}/video`} token={token} />
          <div className="frame-grid">
            {item.findings.frames?.map((frame, index) => (
              <figure key={index}>
                <MediaView
                  path={`/submissions/${item.id}/frames/${index}`}
                  token={token}
                  image
                  alt={`Video sample at ${frame.timestamp_ms / 1000} seconds`}
                />
                <figcaption>
                  {(frame.timestamp_ms / 1000).toFixed(2)} seconds
                </figcaption>
              </figure>
            ))}
          </div>
        </>
      )}
      {item.findings.assessment && (
        <div className="criterion-grid">
          {Object.entries(item.findings.assessment).map(([key, value]) => (
            <div key={key}>
              <strong>
                {key.replaceAll("_", " ")}: {value.result}
              </strong>
              <p>{value.explanation}</p>
            </div>
          ))}
        </div>
      )}
      {item.findings.processing_error && (
        <p role="alert" className="error">
          {item.findings.processing_error}
        </p>
      )}
      {item.findings.provider_error && (
        <p className="notice">
          {item.findings.provider_error} Full-video human review is still
          required.
        </p>
      )}
      {!!(
        (item.findings.exact_duplicate_candidates?.length || 0) +
        (item.findings.perceptual_duplicate_candidates?.length || 0)
      ) && (
        <div className="notice">
          <strong>Possible duplicate pairs</strong>
          <p>
            Compare this submission with{" "}
            {[
              ...new Set([
                ...(item.findings.exact_duplicate_candidates || []),
                ...(item.findings.perceptual_duplicate_candidates || []),
              ]),
            ].join(", ")}{" "}
            in this queue.
          </p>
          <p>{item.findings.duplicate_notice}</p>
        </div>
      )}
      <p className="muted">
        {item.findings.limitations ||
          "Automated checks do not prove ownership, consent, authenticity or task completion."}
      </p>
      {reviewable && (
        <div className="review-form">
          <label className="check">
            <input
              type="checkbox"
              checked={watched}
              onChange={(e) => setWatched(e.target.checked)}
            />
            I watched the full video.
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={completed}
              onChange={(e) => setCompleted(e.target.checked)}
            />
            The video shows a complete towel-folding demonstration.
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={large}
              onChange={(e) => setLarge(e.target.checked)}
            />
            Meets the buyer-approved large-towel definition.
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={dark}
              onChange={(e) => setDark(e.target.checked)}
            />
            Meets the buyer-approved dark-surface definition.
          </label>
          <label htmlFor={`reason-${item.id}`}>Decision reason</label>
          <textarea
            id={`reason-${item.id}`}
            minLength={3}
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            rows={2}
          />
          <button
            className="primary"
            disabled={
              busy ||
              !watched ||
              !completed ||
              !item.findings.decoded ||
              reason.trim().length < 3
            }
            onClick={() => void decide("accept")}
          >
            {item.fixture
              ? "Accept fixture work"
              : "Accept quality; prepare wallet payout"}
          </button>
          <button
            disabled={busy || reason.trim().length < 3}
            onClick={() => void decide("reject")}
          >
            Reject with reason
          </button>
        </div>
      )}
      {item.review_reason && <p>Review decision: {item.review_reason}</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </article>
  );
}

export default function Reviews({ token }: { token?: string }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [items, setItems] = useState<Submission[]>([]);
  const [coverage, setCoverage] = useState<Coverage>();
  const [rubric, setRubric] = useState<{
    requirements: { key: string; description: string }[];
    min_seconds: number;
    max_seconds: number;
  }>();
  const [batchMessage, setBatchMessage] = useState("");
  const [batchRequestId, setBatchRequestId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function loadJobs() {
    if (!token) return;
    setError("");
    setBusy(true);
    try {
      setJobs((await request<{ jobs: Job[] }>("/me/jobs", token)).jobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your jobs");
    } finally {
      setBusy(false);
    }
  }
  async function load(id = selected) {
    if (!token || !id) return;
    setError("");
    setBusy(true);
    try {
      const [queue, counts, job] = await Promise.all([
        request<{ submissions: Submission[] }>(`/jobs/${id}/reviews`, token),
        request<Coverage>(`/jobs/${id}/coverage`, token),
        request<{
          plan: {
            requirements: { key: string; description: string }[];
            min_seconds: number;
            max_seconds: number;
          };
        }>(`/jobs/${id}`, token),
      ]);
      setItems(queue.submissions);
      setCoverage(counts);
      setRubric(job.plan);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load review queue",
      );
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (!token) {
      setJobs([]);
      setItems([]);
      setCoverage(undefined);
      setSelected("");
    }
  }, [token]);
  async function exportManifest() {
    if (!token || !selected) return;
    try {
      const data = await request(`/jobs/${selected}/export`, token);
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `framebounty-${selected}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Export failed");
    }
  }
  async function nextBatch() {
    if (!token || !selected) return;
    const requestId = batchRequestId || crypto.randomUUID();
    setBatchRequestId(requestId);
    setBusy(true);
    setError("");
    try {
      const result = await request<{
        published_slots: number;
        explanation: string;
      }>(
        `/jobs/${selected}/${jobs.find((job) => job.id === selected)?.fixture ? "next-fixture-batch" : "next-batch"}`,
        token,
        {
          request_id: requestId,
        },
      );
      setBatchMessage(
        `${result.published_slots} slots published. ${result.explanation}`,
      );
      setBatchRequestId("");
      await load();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not commission next batch",
      );
    } finally {
      setBusy(false);
    }
  }
  async function exportDataset() {
    if (!token || !selected) return;
    setError("");
    try {
      const picker = (
        window as Window & {
          showSaveFilePicker?: (options: unknown) => Promise<{
            createWritable: () => Promise<WritableStream<Uint8Array>>;
          }>;
        }
      ).showSaveFilePicker;
      const handle = picker
        ? await picker.call(window, {
            suggestedName: `framebounty-${selected}.zip`,
          })
        : undefined;
      const response = await fetch(`${apiBase}/jobs/${selected}/dataset.zip`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!response.ok)
        throw new Error(
          "Dataset export failed. Refresh the collection and retry.",
        );
      if (handle && response.body) {
        await response.body.pipeTo(await handle.createWritable());
      } else {
        if (Number(response.headers.get("X-Data-Bytes")) > 128 * 1024 * 1024) {
          await response.body?.cancel();
          throw new Error(
            "Use desktop Chrome to stream this large dataset directly to a file.",
          );
        }
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url;
        link.download = `framebounty-${selected}.zip`;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Dataset export failed");
    }
  }
  return (
    <section className="panel reviews">
      <p className="eyebrow">HUMAN REVIEW & DATASET COVERAGE</p>
      <h2>Review the work. Know what counts.</h2>
      {!token ? (
        <p>
          Connect and authenticate the designated buyer/reviewer wallet to
          access private submissions.
        </p>
      ) : (
        <>
          <button disabled={busy} onClick={() => void loadJobs()}>
            Load my collections
          </button>
          <label htmlFor="review-job">Collection</label>
          <select
            id="review-job"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              setItems([]);
              setCoverage(undefined);
              if (e.target.value) void load(e.target.value);
            }}
          >
            <option value="">Choose a collection</option>
            {jobs.map((job) => (
              <option key={job.id} value={job.id}>
                {job.title} · {job.fixture ? "fixture" : job.state}
              </option>
            ))}
          </select>
          {selected && (
            <>
              <button disabled={busy} onClick={() => void load()}>
                Refresh queue & coverage
              </button>
              <button onClick={() => void exportManifest()}>
                Export accepted manifest
              </button>
              <button onClick={() => void exportDataset()}>
                Download dataset ZIP
              </button>
              <button disabled={busy} onClick={() => void nextBatch()}>
                {jobs.find((job) => job.id === selected)?.fixture
                  ? "Commission next fixture batch"
                  : "Commission next testnet batch"}
              </button>
            </>
          )}
          {batchMessage && (
            <p className="notice" role="status">
              {batchMessage}
            </p>
          )}
          {rubric && selected && (
            <details>
              <summary>Agreed video rubric</summary>
              <p>
                {rubric.min_seconds}–{rubric.max_seconds} seconds, complete
                towel fold required.
              </p>
              {rubric.requirements.map((r) => (
                <p key={r.key}>{r.description}</p>
              ))}
            </details>
          )}
          {selected && (
            <AgentPane
              key={selected}
              role="buyer"
              token={token}
              jobId={selected}
            />
          )}
          {coverage && (
            <div className="metrics">
              <div>
                <strong>{coverage.accepted_total}</strong>
                <span>accepted clips</span>
              </div>
              <div>
                <strong>{coverage.pending_total}</strong>
                <span>pending commitments</span>
              </div>
              {Object.entries(coverage.accepted_categories).map(
                ([key, value]) => (
                  <div key={key}>
                    <strong>{value}</strong>
                    <span>{key.replaceAll("_", " ")}</span>
                  </div>
                ),
              )}
            </div>
          )}
          {selected && !busy && items.length === 0 && (
            <p className="muted">
              No submissions yet. Contributors must reserve and upload before
              work enters review.
            </p>
          )}
          {items.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              token={token}
              refreshed={() => load()}
            />
          ))}
        </>
      )}
      {busy && <p role="status">Loading…</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
