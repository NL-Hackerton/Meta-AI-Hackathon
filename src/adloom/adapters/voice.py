"""Live Muse Voice transcription through ``/v1/asr/transcribe``."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import httpx

from adloom.adapters.model_api import ModelApi, build_client, require_standard_model
from adloom.config import AdLoomError
from adloom.schemas import Segment, Stage

MODEL = "muse-voice-transcribe-1.0"
SAMPLE_RATE = 16_000
# Documented body cap is 32 MB; leave room for the multipart envelope and request part.
MAX_WAV_BYTES = 31_000_000
MAX_AUDIO_MS = 600_000
LANGUAGE_BIAS = {"ko": "Korean", "en": "English"}


class LiveVoice:
    """VoiceAdapter backed by ``muse-voice-transcribe-1.0`` in ENDPOINTING mode."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        job_dir: Path | None = None,
        model: str = MODEL,
        stage: Stage = "enrich",
    ) -> None:
        if job_dir is None:
            raise AdLoomError("E_INPUT_INVALID", stage, "Voice needs a job directory for audio")
        self.stage: Stage = stage
        self.model = require_standard_model(model, MODEL, stage)
        self.api = ModelApi(api_key, client or build_client())
        self.job_dir = job_dir

    def request_part(self, language: str) -> dict[str, object]:
        if language not in LANGUAGE_BIAS:
            raise AdLoomError("E_INPUT_INVALID", self.stage, "Unsupported transcription language")
        return {
            "model": self.model,
            "audioEncoding": "WAV",
            "mode": "ENDPOINTING",
            "languageBias": [LANGUAGE_BIAS[language]],
        }

    def transcribe(self, media: Path, language: str) -> tuple[Segment, ...]:
        request = self.request_part(language)
        scratch = self.job_dir / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        wav = scratch / f"voice-{uuid4().hex}.wav"
        try:
            extract_wav(media, wav, self.stage)
            size = wav.stat().st_size
            if size > MAX_WAV_BYTES or size > MAX_AUDIO_MS * SAMPLE_RATE * 2 // 1000 + 4096:
                raise AdLoomError("E_RESOURCE_LIMIT", self.stage, "Audio exceeds the upload limit")
            with wav.open("rb") as audio:
                body = self.api.request_json(
                    "POST",
                    "/asr/transcribe",
                    self.stage,
                    "Transcription",
                    files={
                        "request": (None, json.dumps(request).encode(), "application/json"),
                        "audio": ("audio.wav", audio, "audio/wav"),
                    },
                )
        finally:
            wav.unlink(missing_ok=True)
        return segments(body, self.stage)


def extract_wav(media: Path, wav: Path, stage: Stage) -> None:
    """Write RIFF/WAVE, mono, signed 16-bit PCM at 16 kHz with metadata removed."""
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-i",
                str(media),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                "-c:a",
                "pcm_s16le",
                "-map_metadata",
                "-1",
                "-f",
                "wav",
                "-y",
                str(wav),
            ],
            capture_output=True,
            timeout=120,
            check=True,
        )
    except subprocess.SubprocessError:
        raise AdLoomError("E_INPUT_INVALID", stage, "Audio extraction failed") from None


def segments(body: dict[str, object], stage: Stage) -> tuple[Segment, ...]:
    turns = body.get("turns")
    if not isinstance(turns, list):
        raise AdLoomError("E_API_SCHEMA", stage, "Transcription response has no turns")
    result: list[Segment] = []
    for turn in turns:
        if not isinstance(turn, dict):
            raise AdLoomError("E_API_SCHEMA", stage, "Transcription turn is not an object")
        start, end, text = turn.get("startMs"), turn.get("endMs"), turn.get("transcript")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(text, str)
        ):
            raise AdLoomError("E_API_SCHEMA", stage, "Transcription turn has invalid fields")
        if not text.strip():
            # The API reports a turn cut off by the end of the clip with an empty transcript.
            continue
        if start < 0 or end <= start:
            raise AdLoomError("E_API_SCHEMA", stage, "Transcription turn has invalid timing")
        result.append(Segment(start_us=start * 1000, end_us=end * 1000, text=text.strip()))
    return tuple(result)
