# SAM 3.1 live adapter (`src/adloom/adapters/sam.py`)

Docs read on 2026-11-02. No real API call was made; tests use `httpx.MockTransport` with SSE
bodies built from the documented wire grammar and the real mask payloads from the docs and the
`meta-sam-parser` 0.1.0 README (`third_party/meta-sam-parser/meta_sam_parser-0.1.0.tar.gz`).

## Sources

- Segmenting with prompts: https://dev.meta.ai/docs/sam/segmenting
- Reading segmentation output: https://dev.meta.ai/docs/sam/reading-segmentation
- Client libraries: https://dev.meta.ai/docs/sam/client-libraries
- Files: https://dev.meta.ai/docs/file-handling

## Request

`POST /v1/files` (same helper as Spark), then `POST /v1/responses` with
`Accept: text/event-stream`, `Accept-Encoding: identity`:

```json
{
  "model": "sam-3.1",
  "input": [{"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "white ceramic mug"},
    {"type": "input_video", "file_id": "file-abc123"}
  ]}],
  "stream": true,
  "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"}
}
```

- Docs: "`input_video`: a clip as `video_url`, or as `file_id` for a video uploaded through the
  Files API."
- "Metadata values are strings, so send `"true"` rather than a JSON boolean."
- `mask_encoding: "one_bit"`: "The payload is several times smaller than `lossless`".

## Response (SSE)

- "Each frame emits one `response.output_text.delta` event holding one line. The stream terminates
  on `response.completed`." The parser README adds: "The live SAM Model API emits only" the
  `response.content_part.done` finalizer.
- Line grammar: `<Nf>id<|box;x1=..;y1=..;x2=..;y2=..;w=<frameW>;h=<frameH>[;c=<conf>]|><|mask;...|>,...`.
  Documented example used in tests (320×334 clip, frame 0):
  `<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|><|mask;x=0;y=0;data=27,60,~...|>,1<|box;...|>...`
- Frames "may skip frames; not always ascending"; ids are "not dense or 0-based".
- Zero matches: "The stream completes with an empty `output_text` and no
  `response.output_text.delta` events." Treated as a normal result: every box `None`, coverage 0.

## Parsing and selection

- Events are fed to the official `meta_sam_parser.parse_responses_stream(...).final_result()`
  with `video_segmentation_format()`; the parser owns lane validation, refusal/failed/error
  events, and mask decoding. The sync adapter runs it on a private event loop.
- `SegmentationBoxRecord.right/bottom` are already half-open, so `w = right - left`,
  `h = bottom - top` (no `+1`). Wire `x2=270` → `right=271` → width 60, matching the 60-column mask.
- The object present on the most frames wins; ties go to the lowest numeric id. Boxes are laid out
  per probed frame (`None` where absent) and `coverage = frames_with_box / frame_count`, before any
  interpolation. `score` is the box `c` value or `None` ("`None` does not mean zero").
- Width, height, fps and frame count come from `ffprobe -count_frames` on the uploaded normalized
  MP4. Every box token's `w`/`h` must equal that size, frame indices must be inside
  `[0, frame_count)`, and an object repeated on one frame is rejected (`E_API_SCHEMA`).
- Guards from codebase.md §7: total SSE bytes ≤ 64 MiB and physical line ≤ 2 MiB are enforced on
  the raw byte stream before SSE decoding; each event's data ≤ 2 MiB after decoding; any mask
  header `H×W` larger than the source area raises `E_RESOURCE_LIMIT` before the parser decodes it.

## Error mapping

HTTP status before streaming → shared mapping (401/403 auth, 429 rate, ...); non-SSE
`Content-Type` or compressed body → `E_API_SCHEMA`; refusal → `E_API_REFUSED`; `response.failed`
/ `error` event → auth/rate by enumerated `type`/`code`, else `E_API_REMOTE`; `response.incomplete`
or EOF without a terminal event → `E_API_INCOMPLETE`; lane errors, invalid masks, parser
diagnostics, stray text → `E_API_SCHEMA`; no SAM failure is retried with Spark's repair loop.

## Open questions (unverified until the H2 smoke test)

- Whether a zero-match response sends a finalized empty `output_text` lane
  (`response.content_part.done` with `text: ""`) or no lane at all. Both shapes are accepted; the
  lane-less case is detected by catching the parser's lane error only when no lane event was seen
  and the last event was `response.completed`.
- Whether `input_video.file_id` from Files is accepted together with `stream: true` for a
  45-second, 1350-frame clip (documented examples show it; billing is per frame, minimum 50).
- The exact `response.failed` / `error` event payload on SAM; the classification only reads
  `error.type`/`error.code` and defaults to `E_API_REMOTE`.
- The service may losslessly remux a non-faststart MP4 ("Frames and timestamps are unchanged");
  the normalized MP4 should be written with `+faststart` to avoid it (not changed here).
- Uploaded videos persist until `LiveTracking.cleanup()` deletes them; pipeline wiring is pending.
