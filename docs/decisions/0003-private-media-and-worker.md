# 0003: Private raw uploads and fenced verification

Context: phone uploads can be malformed, large, duplicated or interrupted. A worker
can restart while another lease holder is still processing the same submission.

Options: public uploads and in-process background tasks, or private object keys and
PostgreSQL leased jobs. Choice: the latter, using raw MP4/MOV bodies to avoid multipart
filename handling. Uploads require task-specific rights acknowledgment and owner auth.
The final transaction rechecks reservation expiry under job/reservation locks, creates
one submission and durable job, and preserves the committed reward through review.

Workers claim with SKIP LOCKED, process outside transactions, and finish only with a
current unexpired lease token. Three attempts bound recovery. Expired final attempts
become visible failures, never stuck verification or automatic acceptance. Timeout release
and late worker completion cannot resurrect a terminal submission.

Metadata/probe, complete bounded decode, five sampled frames, Pillow metrics, exact hashes
and ImageHash difference hashes assist review. Similarity never rejects repeated tasks.
The designated reviewer must attest full-video playback, task completion and required
category tags. Fixture acceptance changes only a labeled simulated ledger; no payment
receipt is invented. Dataset ZIP exports stream immutable accepted objects with metadata.

Risks: samples can miss actions; perceptual thresholds are heuristics; general vision
does not prove ground truth, consent or authenticity. Native workers enforce process
timeouts and media limits but not a total process-memory ceiling. The opt-in Compose
worker adds a 768 MiB container limit, one CPU and 64 PIDs. Its image/runtime has not
been tested in this Windows session. Run migrations before starting any worker.

Uncertain database COMMIT outcomes preserve private staged media for reconciliation;
automatic orphan-object collection is deferred so a recovery cannot delete a valid upload.
Export responses authorize each request; downloaded files are then outside access control.

Validation: real PostgreSQL/FFmpeg tests cover upload retry, privacy, malformed video,
human completion, review/expiry ordering, overlap accounting, ZIP fidelity, and stale lease
fencing. Chromium covers the complete labeled fixture collection flow at phone viewport.
