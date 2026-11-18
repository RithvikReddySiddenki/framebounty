"use client";

import { useEffect, useState } from "react";
import { apiBase, notifySessionExpired, request } from "./api";
import MediaView from "./media-view";
import WalletAction from "./wallet-action";

export type Submission = {
  id: string;
  media_type: "image" | "video";
  reservation_id: string;
  job_id: string;
  state: string;
  payment_confirmed: boolean;
  fixture: boolean;
  rights_declaration: string;
  review_deadline: string;
  reviewed_tags: string[];
  review_reason: string | null;
  findings: {
    decoded?: boolean;
    processing_error?: string;
    provider_error?: string;
    limitations?: string;
    frames?: {
      timestamp_ms: number;
      brightness: number;
      edge_variance: number;
    }[];
    assessment?: Record<
      string,
      { result: string; explanation: string; timestamps_ms: number[] }
    > | null;
    exact_duplicate_candidates?: string[];
    perceptual_duplicate_candidates?: string[];
    duplicate_notice?: string;
  };
};

export default function Upload({
  reservationId,
  token,
  rights,
  existingId,
  canUpload,
  onChanged,
  mediaType = "video",
}: {
  mediaType?: "image" | "video";
  reservationId: string;
  token: string;
  rights: string;
  existingId?: string | null;
  canUpload: boolean;
  onChanged?: () => Promise<void>;
}) {
  const image = mediaType === "image";
  const [file, setFile] = useState<File>();
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [percent, setPercent] = useState(0);
  const [error, setError] = useState("");
  const [submission, setSubmission] = useState<Submission>();
  const [preview, setPreview] = useState(false);

  async function refresh() {
    const id = submission?.id || existingId;
    if (!id) return;
    setError("");
    try {
      setSubmission(await request<Submission>(`/submissions/${id}`, token));
      await onChanged?.();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not refresh submission",
      );
    }
  }
  useEffect(() => { if (existingId) void refresh(); }, [existingId]);
  useEffect(() => {
    if (!submission || !["queued", "verifying"].includes(submission.state)) return;
    const timer = window.setInterval(() => void refresh(), 3000);
    return () => window.clearInterval(timer);
  }, [submission?.id, submission?.state]);
  async function upload() {
    if (!file || !acknowledged) return;
    if (file.size > (image ? 20 : 100) * 1024 * 1024) {
      setError(image ? "Choose an image smaller than 20 MiB." : "Choose a video smaller than 100 MiB.");
      return;
    }
    setBusy(true);
    setError("");
    setPercent(0);
    try {
      const result = await new Promise<Submission>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open(
          "POST",
          `${apiBase}/reservations/${reservationId}/media?rights_ack=true&model_ack=true`,
        );
        xhr.timeout = 125000;
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.setRequestHeader(
          "Content-Type",
          file.type ||
            (image ? (file.name.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg") : file.name.toLowerCase().endsWith(".mov")
              ? "video/quicktime"
              : "video/mp4"),
        );
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable)
            setPercent(Math.round((event.loaded / event.total) * 100));
        };
        xhr.onerror = () =>
          reject(
            new Error("Upload connection failed. Retry the same video safely."),
          );
        xhr.ontimeout = () =>
          reject(
            new Error(
              "Upload timed out. Check your connection and retry the same video.",
            ),
          );
        xhr.onload = () => {
          if (xhr.status === 401) notifySessionExpired(token);
          let data;
          try {
            data = JSON.parse(xhr.responseText);
          } catch {
            reject(
              new Error("Unexpected upload response; refresh before retrying."),
            );
            return;
          }
          if (xhr.status >= 200 && xhr.status < 300)
            resolve(data as Submission);
          else
            reject(
              new Error(
                typeof data.detail === "string"
                  ? data.detail
                  : "Upload failed; check the file and retry.",
              ),
            );
        };
        xhr.send(file);
      });
      setSubmission(result);
      await onChanged?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="upload-box">
      <p className="muted">
        {image ? "Submit one JPEG/PNG image, at most 20 MiB and 16 megapixels. Follow the post requirements." : "Submit a complete 10-30 second MP4/MOV video, at most 100 MiB. Follow the post requirements."}
      </p>
      <details>
        <summary>Requested usage rights</summary>
        <p>{rights}</p>
      </details>
      {canUpload && !submission && !existingId && (
        <>
          <label htmlFor={`video-${reservationId}`}>{image ? "Choose an image" : "Choose a phone video"}</label>
          <input
            id={`video-${reservationId}`}
            type="file"
            accept={image ? "image/jpeg,image/png,.jpg,.jpeg,.png" : "video/mp4,video/quicktime,.mp4,.mov"}
            disabled={busy}
            onChange={(event) => {
              setFile(event.target.files?.[0]);
              setAcknowledged(false);
            }}
          />
          <label className="check">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)}
              disabled={busy}
            />
            I have read and acknowledge these requested usage rights and have
            permission to submit this media. I consent to sending a reduced image or sampled video frames to Gemini for AI verification.
          </label>
          <button
            className="primary"
            disabled={!file || !acknowledged || busy}
            onClick={() => void upload()}
          >
            {busy ? `Uploading ${percent}%…` : image ? "Upload image" : "Upload video"}
          </button>
          {busy && (
            <progress
              value={percent}
              max={100}
              aria-label="Video upload progress"
            >
              {percent}%
            </progress>
          )}
        </>
      )}
      {(submission || existingId) && (
        <>
          <button disabled={busy} onClick={() => void refresh()}>
            Refresh submission status
          </button>
          <button onClick={() => setPreview(!preview)}>
            {preview ? "Hide media" : image ? "View submitted image" : "Play submitted video"}
          </button>
        </>
      )}
      {submission && (
        <div role="status">
          {!submission.fixture && submission.state === "chain_pending" && (
            <WalletAction
              token={token}
              reservationId={reservationId}
              purpose="submit"
              label="Confirm this uploaded content hash on chain"
              refreshed={refresh}
            />
          )}
          <p>
            <strong>{submission.state.replaceAll("_", " ")}</strong> ·{" "}
            {submission.payment_confirmed
              ? "Payment confirmed"
              : "No chain payment confirmed"}
          </p>
          {submission.review_reason && (
            <p>Reviewer: {submission.review_reason}</p>
          )}
          <p className="muted">
            Review deadline:{" "}
            {new Date(submission.review_deadline).toLocaleString()}
          </p>
          {submission.findings.assessment && <div aria-label="AI verification results"><h4>AI verification</h4>{Object.entries(submission.findings.assessment).map(([key, check]) => <p key={key}><strong>{key.replaceAll("_", " ")}: {check.result}</strong>: {check.explanation}</p>)}</div>}
          {submission.findings.provider_error && <p className="notice">AI verification unavailable: {submission.findings.provider_error} Human review is still required.</p>}
          {submission.findings.processing_error && (
            <p className="error">{submission.findings.processing_error}</p>
          )}
        </div>
      )}
      {preview && (submission?.id || existingId) && (
        <MediaView
          path={`/submissions/${submission?.id || existingId}/media`}
          token={token}
          image={image}
          alt="Submitted image"
        />
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
