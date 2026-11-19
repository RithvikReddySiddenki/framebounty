"use client";

import { useEffect, useState } from "react";
import { apiBase, notifySessionExpired, request } from "./api";
import MediaView from "./media-view";
import AgentPane from "./agent-pane";
import type { Submission } from "./upload";
import ReleaseFunds from "./release-funds";
import Reputation from "./reputation";

type Job = { id: string; title: string; state: string; fixture: boolean };
type Coverage = {
  accepted_total: number;
  pending_total: number;
  accepted_categories: Record<string, number>;
  fixture: boolean;
};

function ReviewCard({ item, token }: { item: Submission; token: string; requirements?: { key: string; description: string }[]; refreshed?: () => Promise<void> }) {
  const [mediaVisible, setMediaVisible] = useState(false);
  return <article className="panel review-card">
    <p className="eyebrow">{item.fixture ? "FIXTURE SUBMISSION" : "TESTNET SUBMISSION"} - {item.state.replaceAll("_", " ")}</p>
    <h3>Submission {item.id.slice(0, 8)}</h3>
    {item.payment_due_at && !item.payment_confirmed && <p className="notice">Automatic payment eligible {new Date(item.payment_due_at).toLocaleString()}. Release sooner in a batch below.</p>}
    {!item.payment_confirmed && item.state !== "fixture_accepted" && <p className="muted">Originals unlock after confirmed payment. Before payment, only reduced watermarked previews are available.</p>}
    <p>{item.payment_confirmed ? "Payment confirmed." : item.state === "verified" ? "AI verification passed. Payment window is shown below." : "No chain payment confirmed."}</p>
    {item.review_reason && <p>{item.review_reason}</p>}
    {item.findings.verification && <p className="notice">{item.findings.verification.reason}</p>}
    <button onClick={() => setMediaVisible(!mediaVisible)}>{mediaVisible ? "Hide submitted media" : item.media_type === "image" ? "View submitted image & AI checks" : "View watermarked preview & AI checks"}</button>
    {mediaVisible && <>
      <MediaView path={`/submissions/${item.id}/${item.payment_confirmed || item.state === "fixture_accepted" ? "media" : "preview"}`} token={token} image={item.media_type === "image" || (!item.payment_confirmed && item.state !== "fixture_accepted")} alt="Submitted image" />
      {item.media_type !== "image" && <div className="frame-grid">{item.findings.frames?.map((frame, index) => <figure key={index}><MediaView path={`/submissions/${item.id}/frames/${index}`} token={token} image alt={`Video sample at ${frame.timestamp_ms / 1000} seconds`} /><figcaption>{(frame.timestamp_ms / 1000).toFixed(2)} seconds</figcaption></figure>)}</div>}
    </>}
    {item.findings.assessment && <div className="criterion-grid">{Object.entries(item.findings.assessment).map(([key, value]) => <div key={key}><strong>{key.replaceAll("_", " ")}: {value.result}{value.confidence !== undefined ? ` (${value.confidence}% model-reported confidence)` : ""}</strong><p>{value.explanation}</p></div>)}</div>}
    {item.findings.processing_error && <p className="error">{item.findings.processing_error}</p>}
    {item.findings.provider_error && <p className="notice">{item.findings.provider_error}</p>}
    <p className="muted">{item.findings.limitations || "AI certainty is not a calibrated probability. Protected posts pay automatically after their payment window."}</p>
    {item.payment_confirmed && <Reputation token={token} submissionId={item.id} />}
  </article>;
}

export default function Reviews({
  token,
  onChanged,
  jobId,
}: {
  token?: string;
  onChanged?: () => Promise<void>;
  jobId?: string;
}) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [items, setItems] = useState<Submission[]>([]);
  const [coverage, setCoverage] = useState<Coverage>();
  const [rubric, setRubric] = useState<{
    requirements: { key: string; description: string }[];
    reward_atomic: string | number;
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
            reward_atomic: string | number;
    min_seconds: number;
            max_seconds: number;
          };
        }>(`/jobs/${id}`, token),
      ]);
      setItems(queue.submissions);
      setCoverage(counts);
      setRubric(job.plan);
      await onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load review queue",
      );
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    if (token && jobId) { setSelected(jobId); void load(jobId); }
  }, [token, jobId]);
  useEffect(() => {
    if (!token) {
      setJobs([]);
      setItems([]);
      setCoverage(undefined);
      setSelected("");
    }
  }, [token]);
  useEffect(() => {
    if (!selected || !token) return;
    let polling = false;
    const timer = window.setInterval(() => { if (!polling) { polling = true; void load().finally(() => { polling = false; }); } }, 3000);
    return () => window.clearInterval(timer);
  }, [selected, token]);
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
      if (response.status === 401) notifySessionExpired(token);
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
      <p className="eyebrow">AUTOMATIC VERIFICATION & FUNDS RELEASE</p>
      <h2>Automatic checks. Protected payment.</h2>
      {!token ? (
        <p>
          Connect and authenticate the designated buyer/reviewer wallet to
          access private submissions.
        </p>
      ) : (
        <>
          {!jobId && <>
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
          </select></>}
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
              <summary>Post requirements</summary>
              <p>
                Videos: {rubric.min_seconds}–{rubric.max_seconds} seconds. Each
                submission is checked automatically against the requirements
                below.
              </p>
              {rubric.requirements.map((r) => (
                <p key={r.key}>{r.description}</p>
              ))}
            </details>
          )}
          {selected && (
            <details><summary>Ask the agent about this post</summary>
            <AgentPane
              key={selected}
              role="buyer"
              token={token}
              jobId={selected}
            />
            </details>
          )}
          {coverage && (
            <div className="metrics">
              <div>
                <strong>{coverage.accepted_total}</strong>
                <span>accepted items</span>
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
          {selected && <ReleaseFunds key={selected} token={token} jobId={selected} count={items.filter(item => ["verified", "release_pending", "accept_pending"].includes(item.state)).length} amountAtomic={String(BigInt(rubric?.reward_atomic || 0) * BigInt(items.filter(item => ["verified", "release_pending", "accept_pending"].includes(item.state)).length))} pending={items.some(item => ["release_pending", "accept_pending"].includes(item.state))} fixture={items[0]?.fixture || false} onChanged={() => load()} />}
          {items.map((item) => (
            <ReviewCard
              key={item.id}
              item={item}
              token={token}
              requirements={rubric?.requirements || []}
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
