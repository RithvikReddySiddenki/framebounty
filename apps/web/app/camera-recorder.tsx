"use client";

import { useEffect, useRef, useState } from "react";
import { request } from "./api";
import {
  cameraErrorMessage,
  MAX_RECORDING_MS,
  MIN_RECORDING_MS,
  recordingExtension,
  recordingMimeType,
  secondsLabel,
} from "./camera";

type Recording = {
  file: File;
  captureToken: string;
  durationMs: number;
  previewUrl: string;
};

export default function CameraRecorder({
  reservationId,
  token,
  disabled,
  onRecording,
}: {
  reservationId: string;
  token: string;
  disabled: boolean;
  onRecording: (recording?: { file: File; captureToken: string }) => void;
}) {
  const liveVideo = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const startedAt = useRef(0);
  const stopTimer = useRef<number | null>(null);
  const tickTimer = useRef<number | null>(null);
  const captureToken = useRef("");
  const [stage, setStage] = useState<"closed" | "ready" | "recording" | "review">("closed");
  const [elapsed, setElapsed] = useState(0);
  const [recording, setRecording] = useState<Recording>();
  const [error, setError] = useState("");

  function stopTracks() {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    if (liveVideo.current) liveVideo.current.srcObject = null;
  }

  function clearTimers() {
    if (stopTimer.current) window.clearTimeout(stopTimer.current);
    if (tickTimer.current) window.clearInterval(tickTimer.current);
    stopTimer.current = null;
    tickTimer.current = null;
  }

  function discardRecording() {
    if (recording?.previewUrl) URL.revokeObjectURL(recording.previewUrl);
    setRecording(undefined);
    onRecording(undefined);
  }

  function cleanup() {
    clearTimers();
    const active = recorder.current;
    if (active?.state === "recording") {
      active.ondataavailable = null;
      active.onstop = null;
      active.onerror = null;
      active.stop();
    }
    recorder.current = null;
    stopTracks();
  }

  useEffect(() => () => {
    cleanup();
    if (recording?.previewUrl) URL.revokeObjectURL(recording.previewUrl);
  }, [recording?.previewUrl]);

  useEffect(() => {
    if (liveVideo.current && stream.current && (stage === "ready" || stage === "recording"))
      liveVideo.current.srcObject = stream.current;
  }, [stage]);

  async function openCamera() {
    setError("");
    discardRecording();
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("This browser cannot record video in FrameBounty. Use a current Chrome, Edge, Firefox, or Safari browser with a camera.");
      return;
    }
    const mime = recordingMimeType((type) => MediaRecorder.isTypeSupported(type));
    if (!mime) {
      setError("This browser has no supported MP4 or WebM camera recorder.");
      return;
    }
    try {
      const opened = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      stream.current = opened;
      try {
        const grant = await request<{ token: string; expires_at: string }>(
          `/reservations/${reservationId}/capture-sessions`,
          token,
          {},
        );
        captureToken.current = grant.token;
        setStage("ready");
      } catch (grantError) {
        stopTracks();
        throw grantError;
      }
    } catch (cameraError) {
      cleanup();
      setStage("closed");
      setError(cameraError instanceof Error && cameraError.name === "Error"
        ? cameraError.message
        : cameraErrorMessage(cameraError));
    }
  }

  function startRecording() {
    if (!stream.current) return;
    setError("");
    discardRecording();
    const mime = recordingMimeType((type) => MediaRecorder.isTypeSupported(type));
    if (!mime) return setError("This browser has no supported MP4 or WebM camera recorder.");
    try {
      const active = new MediaRecorder(stream.current, { mimeType: mime });
      chunks.current = [];
      active.ondataavailable = (event) => {
        if (event.data.size) chunks.current.push(event.data);
      };
      active.onerror = () => {
        cleanup();
        setStage("closed");
        setError("Recording failed. Reopen the camera and try again.");
      };
      active.onstop = () => {
        clearTimers();
        stopTracks();
        const durationMs = Math.min(MAX_RECORDING_MS, performance.now() - startedAt.current);
        const blob = new Blob(chunks.current, { type: mime });
        if (!blob.size) {
          setStage("closed");
          setError("The browser produced an empty recording. Reopen the camera and try again.");
          return;
        }
        const file = new File([blob], `framebounty-${reservationId}.${recordingExtension(mime)}`, { type: mime });
        const next = { file, captureToken: captureToken.current, durationMs, previewUrl: URL.createObjectURL(blob) };
        setElapsed(durationMs);
        setRecording(next);
        setStage("review");
        if (durationMs < MIN_RECORDING_MS) {
          onRecording(undefined);
          setError("Recording is under 10 seconds. Retake it and show the complete task.");
        } else {
          onRecording({ file, captureToken: next.captureToken });
        }
      };
      recorder.current = active;
      startedAt.current = performance.now();
      setElapsed(0);
      setStage("recording");
      active.start(1000);
      tickTimer.current = window.setInterval(() => setElapsed(performance.now() - startedAt.current), 250);
      stopTimer.current = window.setTimeout(() => {
        if (active.state === "recording") active.stop();
      }, MAX_RECORDING_MS);
    } catch (recordError) {
      setError(recordError instanceof Error ? recordError.message : "Recording could not start.");
    }
  }

  function stopRecording() {
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  function retake() {
    cleanup();
    discardRecording();
    captureToken.current = "";
    setElapsed(0);
    setError("");
    setStage("closed");
  }

  return (
    <div className="camera-capture">
      {stage === "closed" && (
        <button className="primary" disabled={disabled} onClick={() => void openCamera()}>
          Open camera
        </button>
      )}
      {(stage === "ready" || stage === "recording") && (
        <>
          <video ref={liveVideo} className="camera-preview" autoPlay muted playsInline aria-label="Live camera preview">
            Your browser does not support live camera preview.
          </video>
          <p className="muted">Keep the full task and your hands visible. Audio is not recorded.</p>
          {stage === "ready" ? (
            <button className="primary" disabled={disabled} onClick={startRecording}>Start recording</button>
          ) : (
            <>
              <p role="timer" aria-live="polite">Recording {secondsLabel(elapsed)} / 30s</p>
              <button disabled={disabled} onClick={stopRecording}>Stop recording</button>
            </>
          )}
        </>
      )}
      {stage === "review" && recording && (
        <>
          <video className="camera-preview" src={recording.previewUrl} controls playsInline preload="metadata" aria-label="Recorded video review">
            Your browser does not support recorded-video review.
          </video>
          <p className="muted">Recorded {secondsLabel(recording.durationMs)}. Review the complete clip before submitting.</p>
          <button disabled={disabled} onClick={retake}>Retake recording</button>
        </>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </div>
  );
}
