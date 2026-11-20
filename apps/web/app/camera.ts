export const MIN_RECORDING_MS = 10_000;
export const MAX_RECORDING_MS = 30_000;

const RECORDING_TYPES = [
  "video/mp4;codecs=avc1.42E01E",
  "video/mp4",
  "video/webm;codecs=vp9",
  "video/webm;codecs=vp8",
  "video/webm",
] as const;

export function recordingMimeType(
  supports: (type: string) => boolean,
): string | undefined {
  return RECORDING_TYPES.find(supports);
}

export function recordingExtension(mime: string): "mp4" | "webm" {
  return mime.toLowerCase().startsWith("video/mp4") ? "mp4" : "webm";
}

export function cameraErrorMessage(error: unknown): string {
  const name = error instanceof Error ? error.name : "";
  if (name === "NotAllowedError")
    return "Camera access was blocked. Allow camera access for FrameBounty in your browser, then try again.";
  if (name === "NotFoundError" || name === "OverconstrainedError")
    return "No usable camera was found. Connect or enable a camera, then try again.";
  if (name === "NotReadableError")
    return "The camera is busy or unavailable. Close other camera apps, then try again.";
  if (name === "SecurityError")
    return "Camera access requires a secure HTTPS connection.";
  return "The camera could not start. Check browser camera permissions and try again.";
}

export function secondsLabel(milliseconds: number): string {
  return `${Math.max(0, Math.ceil(milliseconds / 1000))}s`;
}
