# In-app camera-only contributor capture

## Approved scope

Video contributors must record inside FrameBounty after reserving a task. The ordinary video file picker is removed. Image posts keep their existing JPEG/PNG picker in this slice.

This is a workflow guarantee, not proof that a physical camera is genuine. A modified client, virtual camera, or direct API caller can still fabricate camera-origin claims. FrameBounty must describe the feature as in-app capture rather than authenticity or liveness verification.

## Approach considered

1. **MediaRecorder plus a reservation-bound server capture session (chosen).** Works in modern desktop/mobile browsers, gives an actual live preview and retake flow, and prevents the normal upload endpoint from accepting video without first opening a capture session. Chrome-family browsers generally produce WebM; Safari can produce MP4.
2. **`<input capture>` only.** Smaller change, but browsers may still expose the photo library/file chooser and the app cannot control duration or show a consistent review flow.
3. **Client-side MP4 transcoding.** Produces one format but adds a large WebAssembly payload and heavy phone CPU/memory use. This is unnecessary because the existing FFmpeg worker can decode bounded WebM.

## Task 1: backend capture authorization and WebM support

Acceptance:

- Add migration `0008` and a `CaptureSession` record containing only a token hash, reservation/wallet binding, expiry, and consumed state.
- Add an authenticated endpoint that issues a short-lived token only for an active video reservation owned by the caller.
- Video upload requires `X-Capture-Token`; image upload remains unchanged.
- Token validation and consumption occur in the same transaction as submission finalization. Concurrent reuse cannot create two submissions; exact retry behavior remains idempotent.
- Accept `video/webm` with the EBML header and bounded VP8/VP9/AV1 decoding in addition to existing MP4/MOV codecs.
- Dataset export gives WebM submissions the `.webm` extension.

Tests: targeted real-PostgreSQL submission tests for missing/foreign/expired/reused tokens and WebM header/codec validation. Existing MP4/MOV and image tests must remain valid.

## Task 2: camera-only contributor interface

Acceptance:

- After a video reservation, the contributor sees `Open camera`, not a file input.
- Request `getUserMedia` only after the explicit button click, prefer the environment-facing camera, and do not request microphone access.
- Show a live muted preview, recording timer, stop control, and automatic stop at 30 seconds.
- A recording under 10 seconds cannot be submitted. Valid recordings can be reviewed, retaken, and submitted.
- Select a supported MediaRecorder MIME type at runtime, preferring MP4 when available and otherwise WebM. Send the server-issued token with the upload.
- Stop camera tracks and revoke object URLs on retake, successful upload, unmount, reservation change, and errors.
- Permission denial, missing camera, unsupported MediaRecorder, and recorder failure produce specific recovery guidance.

Tests: component logic is extracted into testable helpers; browser coverage stubs `getUserMedia` and `MediaRecorder`, verifies no file input exists, checks permission denial, short-recording rejection, review/retake, and the capture-token upload header.

## Task 3: integration, documentation, and gates

Acceptance:

- Update CORS for `X-Capture-Token`, `.env` only if a new setting is actually required, architecture, test matrix, demo instructions, workboard, and the external live handoff.
- Update the fixture E2E path to record a deterministic generated media stream rather than populating a file input.
- Run backend targeted tests, web unit/type checks, production build, and the affected Playwright flow. Run wider deterministic suites if the environment is available.
- Inspect the diff for secrets, generated output, stale file-picker language, and unsupported authenticity claims.

## Explicit non-goals

- No liveness prompts, face recognition, anti-deepfake claims, geolocation, audio recording, background recording, or camera activation before user action.
- No public deployment work in this branch.
- No changes to Arc payment rules, contract ABI, rewards, or verification thresholds.
