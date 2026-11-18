"use client";

import { useState } from "react";
import { apiBase, notifySessionExpired, request } from "./api";
import MediaView from "./media-view";
import WalletAction from "./wallet-action";

export type Submission = {
  id: string;
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
}: {
  reservationId: string;
  token: string;
  rights: string;
  existingId?: string | null;
  canUpload: boolean;
  onChanged?: () => Promise<void>;
}) {
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
  async function upload() {
    if (!file || !acknowledged) return;
    if (file.size > 100 * 1024 * 1024) {
      setError("Choose a video smaller than 100 MiB.");
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
          `${apiBase}/reservations/${reservationId}/video?rights_ack=true`,
        );
        xhr.timeout = 125000;
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
        xhr.setRequestHeader(
          "Content-Type",
          file.type ||
            (file.name.toLowerCase().endsWith(".mov")
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
        Fixed phone support, both hands and towel visible. Record a complete
        fold in 10–30 seconds. MP4/MOV, at most 100 MiB.
      </p>
      <details>
        <summary>Requested usage rights</summary>
        <p>{rights}</p>
      </details>
      {canUpload && !submission && !existingId && (
        <>
          <label htmlFor={`video-${reservationId}`}>Choose a phone video</label>
          <input
            id={`video-${reservationId}`}
            type="file"
            accept="video/mp4,video/quicktime,.mp4,.mov"
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
            permission to submit this video.
          </label>
          <button
            className="primary"
            disabled={!file || !acknowledged || busy}
            onClick={() => void upload()}
          >
            {busy ? `Uploading ${percent}%…` : "Upload video"}
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
            {preview ? "Hide video" : "Play submitted video"}
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
          {submission.findings.processing_error && (
            <p className="error">{submission.findings.processing_error}</p>
          )}
        </div>
      )}
      {preview && (submission?.id || existingId) && (
        <MediaView
          path={`/submissions/${submission?.id || existingId}/video`}
          token={token}
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
