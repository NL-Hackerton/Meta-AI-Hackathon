# Muse Spark live adapter (`src/adloom/adapters/spark.py`)

Docs read on 2026-11-02. No real API call was made; all behaviour below is tested only against
`httpx.MockTransport` (`tests/test_live_adapters.py`).

## Sources

- Overview (base URL, Bearer key): https://dev.meta.ai/docs/overview
- Files: https://dev.meta.ai/docs/file-handling, delete: https://dev.meta.ai/docs/api-reference/files/delete-file
- Video understanding: https://dev.meta.ai/docs/video-understanding
- Structured output: https://dev.meta.ai/docs/structured-output
- Responses API: https://dev.meta.ai/docs/protocols/responses
- Error handling: https://dev.meta.ai/docs/error-handling

## Request flow

1. `POST /v1/files` multipart, `purpose=user_data`, `file=@upload.mp4;type=video/mp4`.
   Docs (video-understanding): "Upload the video through the Files API with `purpose` set to
   `"user_data"`" then "Reference the uploaded file by ID in a Responses API request using an
   `input_file` content block." Documented upload response:
   `{"id": "file-842549258569145", "object": "file", "bytes": 245832, ..., "status": "uploaded"}`.
   The adapter sends the generic filename `upload.mp4`, never the customer's file name, and reuses
   the id for the schema-repair retry (same content digest).
2. `POST /v1/responses`:

```json
{
  "model": "muse-spark-1.3",
  "store": false,
  "instructions": "<fixed English planning rules>",
  "input": [{"type": "message", "role": "user", "content": [
    {"type": "input_text", "text": "Ad language ... duration ... digests ... owner note [... validation error]"},
    {"type": "input_file", "file_id": "file-..."}
  ]}],
  "text": {"format": {"type": "json_schema", "name": "adloom_understanding",
                       "schema": {...}, "strict": true}}
}
```

- Structured output: "`text.format` is the Responses API parameter for structured output.
  `response_format` is the Chat Completions equivalent ... A parameter from the other endpoint does
  not configure structured output". The adapter never sends `response_format`.
- `store: false` and `instructions` are documented on the Responses page ("set `store: false` so
  the server keeps no copy of the conversation"; `instructions` "is equivalent to sending a
  `developer`-role message").
- Response: `output[]` items; the adapter concatenates `message.content[].text` of type
  `output_text` (documented example: `{"type": "output_text", "text": "...", "annotations": []}`),
  and returns the raw text for `stages/understand.py` to validate and repair once.

## Strict schema

Docs: with `strict: true` "every object must set `additionalProperties: false`", "an object's
`required` array must list every key in its `properties`", "`allOf` and `oneOf`: not supported
anywhere ...; `anyOf` is supported below the root". `strict_schema()` therefore takes
`Understanding.model_json_schema()`, drops `policy_flags` (always recomputed locally by
`adloom.policy`), lists every property as required, rewrites the evidence `oneOf` to `anyOf`, and
drops `title`/`default`/`discriminator` annotations.

## Error mapping (shared, `model_api.py`)

401/403 → `E_API_AUTH`; 429 → `E_API_RATE` (retryable); 413 or `payload_too_large` →
`E_RESOURCE_LIMIT`; `content_policy_violation` → `E_API_REFUSED`; other 4xx → `E_API_REMOTE`;
5xx → `E_API_REMOTE` (retryable); malformed/non-object JSON → `E_API_SCHEMA`; `status:
"incomplete"` → `E_API_INCOMPLETE`; `refusal` content part → `E_API_REFUSED`; transport errors →
`E_API_NETWORK` (retryable only for connect failures, where nothing reached the server). Error
details carry only the HTTP status and enumerated `error.type`/`error.code` tokens, never the
provider `message`.

## Open questions (unverified until the H2 smoke test)

- Whether `strict: true` accepts the remaining pydantic keywords (`pattern`, `minLength`,
  `maxLength`, `minItems`, `maxItems`, `maximum`, `exclusiveMinimum`, `const`, `$ref`/`$defs`).
  The docs list only the subset rules above; a `400` here means stripping them and relying on the
  local validation retry.
- Spark video duration/frame limits are not documented; the 45 s product cap is still ours.
- Whether a refusal arrives as a `refusal` content part on non-streaming Responses (assumed from
  the OpenAI-compatible shape; not shown on the Meta pages).
- `video/mp4` is the only documented video MIME type for Files; the normalized input is MP4.
- Files "don't expire": `LiveSpark.cleanup()` deletes uploads via `DELETE /v1/files/{file_id}`,
  but the pipeline does not call it yet (wiring is out of scope); deletion timing needs the
  retention decision recorded in verification.md §2.
- The model is asked to cite the provided SHA-256 digests in `claims[].references`; whether it
  copies them exactly is unmeasured (invalid evidence is still caught by `assess_evidence`).
