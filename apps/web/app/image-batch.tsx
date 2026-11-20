"use client";

import { useEffect, useRef, useState } from "react";
import { apiBase, notifySessionExpired } from "./api";
import { confirmUploadedSubmission } from "./submit-flow";

type Slot = { id: string; title?: string; expires_at: string; rights_declaration: string };
type Assignment = { slot: Slot; file: File };

/** One original, verification result and fixed reward per reserved image.
 * Never upload an archive or combine images into one payable submission. */
export default function ImageBatch({ token, slots, onChanged }: {
  token: string; slots: Slot[]; onChanged: () => Promise<void>;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [count, setCount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [completed, setCompleted] = useState(0);
  const [error, setError] = useState("");
  const assignment = useRef<Assignment[]>([]);
  const done = useRef(new Set<string>());
  const controller = useRef<AbortController | undefined>(undefined);
  useEffect(() => () => controller.current?.abort(), []);
  const maximum = Math.min(files.length, slots.length, 20);

  function select(list: FileList | null) {
    const images = Array.from(list || []).filter(f => /\.(?:jpe?g|png)$/i.test(f.name))
      .sort((a, b) => (a.webkitRelativePath || a.name).localeCompare(b.webkitRelativePath || b.name)).slice(0, 20);
    setFiles(images); setCount(Math.min(images.length, slots.length, 20) || 1);
    assignment.current = []; done.current.clear(); setCompleted(0);
    setError(images.length ? "" : "Choose a folder or files containing JPEG or PNG images.");
  }

  async function submit() {
    if (busy || !maximum) return;
    setBusy(true); setError("");
    controller.current = new AbortController();
    try {
      if (!assignment.current.length) {
        const selected = files.slice(0, Math.min(count, maximum));
        if (selected.some(f => !f.size || f.size > 20 * 1024 * 1024)) throw new Error("Each image must be nonempty and at most 20 MiB. No images have been sent.");
        assignment.current = selected.map((file, index) => ({ file, slot: slots[index] }));
      }
      for (const { slot, file } of assignment.current) {
        if (done.current.has(slot.id)) continue;
        // Retrying retains this exact file/reservation mapping. The existing
        // server hash check safely reconciles uploads whose response was lost.
        const response = await fetch(`${apiBase}/reservations/${slot.id}/image?rights_ack=true&model_ack=true`, {
          method: "POST", headers: { Authorization: `Bearer ${token}`,
            "Content-Type": /\.png$/i.test(file.name) ? "image/png" : "image/jpeg" },
          body: file, signal: AbortSignal.timeout(125000),
        });
        if (response.status === 401) notifySessionExpired(token);
        if (!response.ok) {
          const payload = await response.json().catch(() => ({}));
          throw new Error(typeof payload.detail === "string" ? payload.detail : "An image upload failed. Retry to continue the same batch.");
        }
        const uploaded = await response.json();
        if (!uploaded.fixture && uploaded.state === "chain_pending") {
          await confirmUploadedSubmission(token, slot.id, controller.current.signal);
        }
        done.current.add(slot.id); setCompleted(done.current.size);
      }
      await onChanged();
      assignment.current = []; done.current.clear(); setCompleted(0); setFiles([]); setCount(1);
    } catch (err) { setError(err instanceof Error ? err.message : "Upload interrupted. Retry this same batch."); }
    finally { setBusy(false); }
  }

  return <section className="panel" aria-label="Upload image batch">
    <h2>Submit multiple images</h2>
    {slots[0]?.title && <p><strong>{slots[0].title}</strong></p>}
    <p>{slots.length} confirmed image reservations available for this task. Choose a folder or individual images, then choose how many to submit. Maximum 20 images per batch.</p>
    <label>Choose image folder<input type="file" accept="image/jpeg,image/png" multiple
      {...{ webkitdirectory: "", directory: "" }} disabled={busy || completed > 0} onChange={e => select(e.target.files)} /></label>
    <label>Or choose image files<input type="file" accept="image/jpeg,image/png" multiple
      disabled={busy || completed > 0} onChange={e => select(e.target.files)} /></label>
    {files.length > 0 && <>
      <label>Number of images to submit<input type="number" min={1} max={maximum} value={count}
        disabled={busy || assignment.current.length > 0} onChange={e => setCount(Math.max(1, Math.min(maximum, Math.floor(Number(e.target.value)) || 1)))} /></label>
      <p>{files.length} images selected. The first {Math.min(count, maximum)} listed below will be submitted.</p>
      <ol>{files.slice(0, Math.min(count, maximum)).map((f, i) => <li key={i}>{f.webkitRelativePath || f.name}</li>)}</ol>
    </>}
    <details><summary>Usage rights</summary><p>{slots[0]?.rights_declaration}</p></details>
    <p>By submitting, you confirm these usage rights for every selected image and consent to AI verification. Each image keeps its own reward and result. We guide you through the required Circle approvals automatically.</p>
    <button className="primary" disabled={busy || !maximum} onClick={() => void submit()}>{busy ? `Uploading ${completed}/${count}…` : completed ? "Continue image batch" : `Submit ${Math.min(count, maximum) || 0} images`}</button>
    {completed > 0 && <p role="status">{completed} images uploaded. Complete any pending on-chain confirmations in their submission cards.</p>}
    {error && <p role="alert" className="error">{error}</p>}
  </section>;
}
