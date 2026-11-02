# Muse Voice live adapter (`src/adloom/adapters/voice.py`)

Docs read on 2026-11-02. No real API call was made; tests use `httpx.MockTransport`.

## Sources

- Speech to text: https://dev.meta.ai/docs/speech-to-text
- Transcribe reference: https://dev.meta.ai/docs/api-reference/voice/transcribe
- Voice schemas: https://dev.meta.ai/docs/api-reference/voice/schemas

## Request

1. `ffmpeg -nostdin -protocol_whitelist file,pipe -i <media> -vn -ac 1 -ar 16000 -c:a pcm_s16le
   -map_metadata -1 -f wav <job>/tmp/voice-<uuid>.wav` (deleted after the call). Docs: "The
   endpoint accepts a RIFF/WAVE container with mono, 16-bit integer PCM at 16 kHz or 24 kHz", and
   the documented conversion uses `-ac 1 ... -c:a pcm_s16le -map_metadata -1`.
2. `POST /v1/asr/transcribe` multipart with `Accept: application/json`:

```text
request = {"model":"muse-voice-transcribe-1.0","audioEncoding":"WAV","mode":"ENDPOINTING","languageBias":["Korean"]}; type=application/json
audio   = @audio.wav; type=audio/wav
```

- Documented Python example: `files={"request": (None, json.dumps({...}), "application/json"),
  "audio": ("recording.wav", audio, "audio/wav")}`.
- `audioEncoding`: "`enum ('WAV')` ... There is no default".
- `languageBias`: "each as a language name, e.g. `["English", "French"]`" — `ko` → `Korean`,
  `en` → `English`; it is a hint, not a forced language.
- `ENDPOINTING`: "Model-detected turn boundaries, one turn per detected speech segment";
  `PUSH_TO_TALK` returns empty `turns`.

## Response

```json
{"sessionId": "9f1c...", "transcript": "...", "audioDurationMs": 8240,
 "turns": [{"turnId": 1, "startMs": 1520, "endMs": 4640, "transcript": "How is the weather?"}]}
```

Each turn becomes `Segment(start_us=startMs*1000, end_us=endMs*1000, text=transcript.strip())`.
Empty transcripts are dropped (docs: "A turn the clip ended part-way through carries the boundaries
the model gave and an empty transcript"); a non-empty turn with `endMs <= startMs` is
`E_API_SCHEMA`.

## Limits and errors

- "Request body exceeds 32 MB → 413", "Audio exceeds 10 minutes → 400": the adapter rejects WAV
  files above 31,000,000 bytes or about 10 minutes of 16 kHz mono PCM with `E_RESOURCE_LIMIT`
  before sending.
- Shared HTTP mapping (401/403 auth, 429 rate, 413 resource limit, 5xx retryable remote).

## Open questions (unverified until the H2 smoke test)

- Turn boundaries are "Audio processed when the model detected ... Not a precise acoustic
  boundary"; subtitle timing accuracy on real store audio is unmeasured.
- Whether `ENDPOINTING` is available for `muse-voice-transcribe-1.0` ("Mode availability depends
  on the model").
- Korean recognition quality and whether 16 kHz (resampled server-side) is worse than the native
  24 kHz.
- The adapter's error stage defaults to `enrich`; construct it with `stage="input"` for the
  owner-note path.
