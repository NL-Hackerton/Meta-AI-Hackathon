# Muse Image live adapter (`src/adloom/adapters/image.py`)

Docs read on 2026-11-02. No real API call was made; tests use `httpx.MockTransport`.

## Sources

- Image generation: https://dev.meta.ai/docs/image-generation
- Error handling: https://dev.meta.ai/docs/error-handling

## Request

`POST /v1/images/generations`:

```json
{
  "model": "muse-image-1.0",
  "prompt": "Background scene for a short advertisement about: <product>. ... No text, no letters, ...",
  "n": 1,
  "size": "1080x1920",
  "response_format": "b64_json",
  "output_format": "png",
  "tool_enablement": {"enable_image_search": false, "enable_web_search": false, "enable_shell": false}
}
```

- "`size`: a `"WxH"` string ... It sets the aspect ratio, not the exact pixel size".
- "`response_format`: `"b64_json"` (default) returns base64 bytes in `data[].b64_json`".
- "`output_format`: `"webp"` (default), `"png"`, or `"jpeg"`. The response echoes the format".
- "The images endpoints expose the same controls as top-level request fields: a `tool_enablement`
  object (with `enable_image_search`, `enable_web_search`, and `enable_shell`)".
- "Unsupported `size`: aspect ratios beyond 16:1 return `400`" — rejected locally first.
- The prompt never asks for text; all words are drawn later by code (SPEC §4.4).

## Response

```json
{"created": 1784584435, "data": [{"b64_json": "UklGR..."}], "output_format": "webp",
 "background": "opaque", "usage": {...}}
```

The adapter requires exactly one `data` item, `output_format` absent or `png`, strict base64, and
a decoded PNG. Pillow `DecompressionBombWarning` is an error and decoded images above
16,777,216 pixels raise `E_RESOURCE_LIMIT`; the JSON body is capped at 32 MiB. The image is
converted to RGB, scaled and center-cropped (`ImageOps.fit`, Lanczos) to the exact requested size,
and written atomically to `<job>/images/<sha256(prompt:size)>.png` (same naming as the mock).

## Error mapping

Shared mapping; additionally `400` with `code: content_policy_violation` → `E_API_REFUSED`.
Docs: "A content-safety block returns `400` (`code: content_policy_violation`, `param: prompt`)",
"a generation failure that Muse Image reports as retryable returns `503`" (→ retryable
`E_API_REMOTE`).

## Open questions (unverified until the H2 smoke test)

- The returned pixel size for `1080x1920`, `1080x1350`, `1080x1080`; the crop may remove edges if
  the generator's aspect differs slightly.
- Whether `tool_enablement` with all three tools off changes quality noticeably for product
  scenes; it is the privacy boundary proposed in SC-008.
- Korean product names in the English prompt template are untested for prompt quality.
