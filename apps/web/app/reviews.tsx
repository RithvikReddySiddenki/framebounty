"use client";

import { useEffect, useState } from "react";
import { apiBase, notifySessionExpired, request } from "./api";
import MediaView from "./media-view";
import AgentPane from "./agent-pane";
import type { Submission } from "./upload";
import ReleaseFunds from "./release-funds";
import Reputation from "./reputation";
import { ITEM_STEPS, Icon, Lifecycle, StatePill, itemProgress, verdict } from "./ui";

type Job = { id: string; title: string; state: string; fixture: boolean };
type Coverage = {
  accepted_total: number;
  pending_total: number;
  accepted_categories: Record<string, number>;
  fixture: boolean;
};

function ReviewCard({ item, token }: { item: Submission; token: string; requirements?: { key: string; description: string }[]; refreshed?: () => Promise<void> }) {
  const [mediaVisible, setMediaVisible] = useState(false);
  const result = verdict(item.state);
  return <article className="panel review-card">
    <div className="spread">
      <div>
        <p className="eyebrow">{item.fixture ? "FIXTURE SUBMISSION" : "TESTNET SUBMISSION"} - {item.state.replaceAll("_", " ")}</p>
        <h3>Submission <span className="mono">{item.id.slice(0, 8)}</span></h3>
      </div>
      <div className="verdict-wrap">
        <span className={`verdict tone-${result.tone}`}><Icon name={result.tone === "ok" ? "check" : result.tone === "danger" ? "x" : "clock"} />{result.label}</span>
        <StatePill state={item.state} />
      </div>
    </div>
    <Lifecycle steps={ITEM_STEPS} progress={itemProgress("reserved", item.state, item.payment_confirmed)} label={`Lifecycle for submission ${item.id.slice(0, 8)}`} />
    <p>{item.payment_confirmed ? "Payment confirmed." : item.state === "verified" ? "AI verification passed. Payment window is shown below." : "No chain payment confirmed."}</p>
    {item.payment_due_at && !item.payment_confirmed && <p className="notice">Automatic payment eligible {new Date(item.payment_due_at).toLocaleString()}. Release sooner in a batch below.</p>}
    {item.review_reason && item.review_reason !== item.findings.verification?.reason && <p className="muted">{item.review_reason}</p>}
    {item.findings.verification && <p className="notice">{item.findings.verification.reason}</p>}
    {item.findings.assessment && <div className="checks">{Object.entries(item.findings.assessment).map(([key, value]) => <div key={key} className={`check check-${value.result}`}>
      <span className="check-icon"><Icon name={value.result === "pass" ? "check" : value.result === "fail" ? "x" : "info"} /></span>
      <div className="check-body">
        <strong>{key.replaceAll("_", " ")}: {value.result}</strong>
        <p>{value.explanation}</p>
      </div>
      {value.confidence !== undefined && <div className="check-conf"><span className="mono">{value.confidence}% model-reported confidence</span><div className="bar"><i style={{ width: `${value.confidence}%` }} /></div></div>}
    </div>)}</div>}
    {item.findings.processing_error && <p className="error">{item.findings.processing_error}</p>}
    {item.findings.provider_error && <p className="notice">{item.findings.provider_error}</p>}
    <button onClick={() => setMediaVisible(!mediaVisible)}><Icon name="eye" />{mediaVisible ? "Hide submitted media" : item.media_type === "image" ? "View submitted image & AI checks" : "View watermarked preview & AI checks"}</button>
    {mediaVisible && <>
      {!item.payment_confirmed && item.state !== "fixture_accepted" && <p className="muted" style={{ marginTop: 10 }}>Originals unlock after confirmed payment. Before payment, only reduced watermarked previews are available.</p>}
      <MediaView path={`/submissions/${item.id}/${item.payment_confirmed || item.state === "fixture_accepted" ? "media" : "preview"}`} token={token} image={item.media_type === "image" || (!item.payment_confirmed && item.state !== "fixture_accepted")} alt="Submitted image" />
      {item.media_type !== "image" && <div className="frame-grid">{item.findings.frames?.map((frame, index) => <figure key={index}><MediaView path={`/submissions/${item.id}/frames/${index}`} token={token} image alt={`Video sample at ${frame.timestamp_ms / 1000} seconds`} /><figcaption>{(frame.timestamp_ms / 1000).toFixed(2)} s</figcaption></figure>)}</div>}
    </>}
    <p className="muted" style={{ marginTop: 12 }}>{item.findings.limitations || "AI certainty is not a calibrated probability. Protected posts pay automatically after their payment window."}</p>
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
    total?: number;
    requirements: { key: string; description: string; minimum?: number }[];
    reward_atomic: string | number;
    min_seconds: number;
    max_seconds: number;
  }>();
  // Fixture flag of the selected job, from /jobs/{id}. The `jobs` list is only
  // loaded in standalone mode, so it can't be relied on inside a post detail.
  const [jobFixture, setJobFixture] = useState<boolean>();
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
          fixture?: boolean;
          plan: {
            total?: number;
            requirements: { key: string; description: string; minimum?: number }[];
            reward_atomic: string | number;
    min_seconds: number;
            max_seconds: number;
          };
        }>(`/jobs/${id}`, token),
      ]);
      setItems(queue.submissions);
      setCoverage(counts);
      setRubric(job.plan);
      setJobFixture(job.fixture);
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
        `/jobs/${selected}/${(jobFixture ?? jobs.find((job) => job.id === selected)?.fixture) ? "next-fixture-batch" : "next-batch"}`,
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
  const releasable = items.filter(item => ["verified", "release_pending", "accept_pending"].includes(item.state));
  const fixtureJob = jobFixture ?? jobs.find((job) => job.id === selected)?.fixture ?? items[0]?.fixture ?? false;
  const pct = (value: number, of?: number) => `${Math.min(100, of ? (value / of) * 100 : value > 0 ? 100 : 0)}%`;
  // Display-only coverage summary derived from data already loaded above.
  const total = rubric?.total || 0;
  const accepted = coverage?.accepted_total || 0;
  const inFlight = coverage?.pending_total || 0;
  const remaining = Math.max(0, total - accepted - inFlight);
  const percent = total ? Math.min(100, Math.round((accepted / total) * 100)) : 0;
  const requirementRows = (rubric?.requirements || []).map(r => ({ ...r, value: coverage?.accepted_categories[r.key] || 0 }));
  const met = requirementRows.filter(r => r.minimum !== undefined && r.value >= r.minimum).length;
  return (
    <section className="panel reviews">
      <p className="eyebrow">Automatic verification & funds release</p>
      <h2>Coverage & submissions</h2>
      {!token ? (
        <p>Connect and authenticate the designated buyer/reviewer wallet to access private submissions.</p>
      ) : (
        <>
          {!jobId && <>
            <button disabled={busy} onClick={() => void loadJobs()}>Load my collections</button>
            <label htmlFor="review-job">Collection</label>
            <select id="review-job" value={selected} onChange={(e) => {
              setSelected(e.target.value); setItems([]); setCoverage(undefined);
              if (e.target.value) void load(e.target.value);
            }}>
              <option value="">Choose a collection</option>
              {jobs.map((job) => <option key={job.id} value={job.id}>{job.title} · {job.fixture ? "fixture" : job.state}</option>)}
            </select>
          </>}
          {selected && <section className="coverage-card" aria-label="Coverage">
            <div className="cov-head">
              <div>
                <p className="eyebrow">Dataset coverage</p>
                <h3>How close is this dataset to done?</h3>
              </div>
              <button disabled={busy} onClick={() => void load()}>Refresh queue & coverage</button>
            </div>
            {coverage ? <>
              <div className="cov-hero">
                <div className="cov-total">
                  {/* The label shares a parent with the count (E2E reads the count via the label's parent). */}
                  <p className="cov-number mono">{accepted}<small>/ {total || "—"}</small></p>
                  <span className="cov-caption">accepted items</span>
                  <span className="cov-caption"> · {percent}% complete</span>
                </div>
                <dl className="cov-facts">
                  <div><dt>In progress</dt><dd className={`mono ${inFlight ? "tone-text-warn" : ""}`}>{inFlight}</dd><span>reserved or verifying</span></div>
                  <div><dt>Still needed</dt><dd className="mono">{remaining}</dd><span>open for contributors</span></div>
                  <div><dt>Requirements met</dt><dd className={`mono ${requirementRows.length && met === requirementRows.length ? "tone-text-money" : ""}`}>{met}<small>/ {requirementRows.length}</small></dd><span>minimums reached</span></div>
                </dl>
              </div>
              <div className="cov-bar" role="img" aria-label={`${accepted} accepted and ${inFlight} in progress out of ${total}`}>
                <i className="cov-accepted" style={{ width: pct(accepted, total) }} />
                <i className="cov-pending" style={{ width: pct(inFlight, total) }} />
              </div>
              <div className="cov-legend"><span><i className="cov-accepted" />Accepted</span><span><i className="cov-pending" />In progress</span><span><i />Remaining</span></div>
              <div className="cov-rows">
                {requirementRows.map(r => {
                  const done = r.minimum !== undefined && r.value >= r.minimum;
                  return <div className="cov-row" key={r.key}>
                    <span className="cov-label" title={r.description}>{r.description}</span>
                    <div className="bar"><i style={{ width: pct(r.value, r.minimum) }} /></div>
                    <strong className="mono">{r.value}{r.minimum !== undefined ? ` / ${r.minimum}` : ""}</strong>
                    {r.minimum !== undefined && <span className={`pill ${done ? "tone-ok" : "tone-warn"}`}>{done ? "Met" : `${r.minimum - r.value} to go`}</span>}
                  </div>;
                })}
              </div>
              <p className="muted cov-note">One clip can count toward several requirements, so requirement totals can add up to more than the accepted count.</p>
            </> : <p className="muted">Loading coverage…</p>}
          </section>}
          {selected && <div className="review-toolbar">
            <button onClick={() => void exportManifest()}>Export accepted manifest</button>
            <button onClick={() => void exportDataset()}>Download dataset ZIP</button>
            <button disabled={busy} onClick={() => void nextBatch()}><Icon name="spark" />{fixtureJob ? "Commission next fixture batch" : "Commission next testnet batch"}</button>
          </div>}
          {batchMessage && <p className="notice" role="status">{batchMessage}</p>}
          {selected && (
            <details><summary>Ask the agent about this collection</summary>
              <AgentPane key={selected} role="buyer" token={token} jobId={selected} />
            </details>
          )}
          {selected && <ReleaseFunds key={selected} token={token} jobId={selected} count={releasable.length} amountAtomic={String(BigInt(rubric?.reward_atomic || 0) * BigInt(releasable.length))} pending={items.some(item => ["release_pending", "accept_pending"].includes(item.state))} fixture={fixtureJob} onChanged={() => load()} />}
          {selected && !busy && items.length === 0 && (
            <div className="empty" style={{ marginTop: 12 }}><Icon name="upload" /><p>No submissions yet. Contributors must reserve and upload before work enters review.</p></div>
          )}
          {items.map((item) => <ReviewCard key={item.id} item={item} token={token} requirements={rubric?.requirements || []} refreshed={() => load()} />)}
        </>
      )}
      {busy && <p role="status" className="muted">Loading…</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
