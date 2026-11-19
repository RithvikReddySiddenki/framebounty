# Agent-led image and video posts

The buyer should describe desired data, review one generated post and authorize
its fixed budget. Requiring a separate conversation, plan editor and manual job
loader obscured whether a post was actually accepting work. The original video
demo also silently shaped unrelated requests around towel-folding criteria.

Plans now carry `media_type: image | video`; absent values remain legacy videos.
The field lives inside the existing immutable JSON plan and its hash. Existing
saved plans/hashes are preserved; there is no database or contract migration.
New posts use their own title, requirements, quotas and usage rights. The agent
proposes a plan; deterministic validation and explicit buyer approval still
precede saving and wallet-owned funding. Fixture planning remains a labeled fixed
towel-video or cat-image example, not a general model interpreter.

The default buyer interface is request -> editable post preview -> approve/save
-> guided wallet publishing. Advanced conversation controls are disclosed on
demand. Owned posts load automatically with their media type and server-derived
draft, awaiting-funding, open or no-available-tasks status. Open requires usable
funds and unclaimed, unexpired task slots; saving a plan never publishes it.

Image submissions accept still JPEG/PNG, at most 20 MiB, 16 megapixels and 8192px
per side, minimum 240px per side. Pillow fully decodes them, rejects animations
and MIME/content mismatches, and creates a metadata-free bounded JPEG sample.
Video submissions retain the bounded 10-30 second MP4/MOV path, including actual
post duration checks. Originals remain private. Generic `/media` upload/download
routes coexist with legacy video aliases. Exports preserve image/video file
extensions and include post media type. No storage keys become public URLs.

The durable worker automatically checks actual post criteria through Gemini.
Only reduced JPEG samples leave local storage, and only with operator
`ALLOW_MODEL_MEDIA=true` and per-submission contributor consent. Consent survives
worker retries. Legacy submissions without consent are not silently uploaded.
Provider failures stay visible; fixture findings are uncertain and explicit.
Model criteria and cited sample timestamps are strictly validated. Similarity is
a review flag. Images cannot prove a complete temporal action or authenticity.

AI pass/fail/uncertain findings assist review; they cannot accept submissions or
pay contributors. A designated human inspects the entire image/video, confirms
post requirements and signs settlement. The legacy `watched_full_video` API
field now means explicit full-media inspection for image posts too; retaining
the field avoids breaking existing signed-in clients. No signing keys enter
model context.

Validation: real PostgreSQL/private upload/Pillow/FFmpeg tests cover both formats,
wrong types, corruption, image bounds/animation, consent, authorization, generic
video criteria, empty task slots and ZIP bytes. A real local-EVM image flow tests
funding, reservation, content-hash commitment and exactly-once payout. Chromium
covers prompt-to-image-post, contributor-agent search, upload, automatic findings
and review alongside the video/export and authentication regressions. A separate
live Gemini smoke generated a 20-image cat-climbing plan and failed a generated
green color card against its criteria. This is connection/schema evidence, not
real task accuracy or proof of an Arc user-funded image payout.
