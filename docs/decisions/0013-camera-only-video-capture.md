# 0013: Reservation-bound in-app video capture

Date: 2026-11-20

## Context

The team requires contributors to record video inside FrameBounty after accepting a
task. A normal file input can expose a gallery or filesystem and does not provide a
consistent duration, review or retake experience. Image posts are not part of this
change and continue to use JPEG/PNG selection.

## Decision

The contributor UI exposes **Open camera** only after a video reservation. Camera
permission is requested from that explicit action with an environment-facing video
preference and `audio: false`. `MediaRecorder` prefers MP4 when supported and falls
back to WebM. The UI provides a muted live preview, timer, manual/automatic stop,
10-30 second enforcement, review and retake.

The API issues a short-lived random capture token only for an active video
reservation owned by the authenticated wallet. Migration 0008 stores its SHA-256
digest, reservation/wallet binding, expiry and consumed state. Video finalization
requires `X-Capture-Token`; token validation and consumption share the submission
transaction and exact retries remain idempotent. WebM receives bounded header,
codec and FFmpeg validation alongside existing MP4/MOV support. Images do not need
a capture token.

Remote camera access requires HTTPS because `getUserMedia` is restricted to secure
contexts. Localhost remains suitable for desktop development under browser rules.

## Alternatives rejected

- `<input capture>` is smaller but can still expose existing media and gives the
  app little control over duration or review.
- Client-side MP4 transcoding adds substantial download, memory and CPU cost on
  phones while the existing worker can safely decode bounded WebM.
- Mandatory liveness prompts or camera-origin proof exceed this product slice and
  would create security/privacy claims the implementation cannot support.

## Security boundary

This enforces the supported application workflow; it does not prove that pixels
came from a genuine physical camera. Virtual cameras, screen-fed cameras, modified
clients and direct API callers can fabricate origin. The product must not describe
this feature as liveness, anti-deepfake or provenance verification.

## Validation

Targeted real-PostgreSQL submission/image tests: 20 passed. Media tests: 25 passed.
Web helper tests: 14 of 14 passed. Web typecheck and production build passed. One
affected Chromium flow passed with deterministic camera/recorder stubs. Physical
phone capture, remote HTTPS operation and camera authenticity are not proven.
