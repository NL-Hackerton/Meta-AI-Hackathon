import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from adloom.adapters.base import VoiceAdapter
from adloom.config import AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import Brief, FrameRate, MediaInfo


def validate_duration(seconds: float) -> None:
    if not math.isfinite(seconds) or not 3 <= seconds <= 45:
        raise AdLoomError("E_INPUT_INVALID", "input", "Video must be 3 to 45 seconds")


def probe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise AdLoomError("E_INPUT_INVALID", "input", "Media file does not exist")
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe", "-count_frames",
            "-show_streams", "-show_format", "-of", "json", str(path),
        ], capture_output=True, timeout=60, check=True)
        value: dict[str, Any] = json.loads(result.stdout)
        return value
    except (subprocess.SubprocessError, ValueError):
        raise AdLoomError("E_INPUT_INVALID", "input", "Media probe failed") from None


def fill_note(brief: Brief, job_dir: Path, voice: VoiceAdapter) -> Brief:
    if brief.note_text is not None:
        return brief
    if brief.note_audio_path is None:
        raise AdLoomError("E_INPUT_INVALID", "input", "An explanation is required")
    source = (job_dir / brief.note_audio_path).resolve()
    if not source.is_relative_to(job_dir.resolve()):
        raise AdLoomError("E_INPUT_INVALID", "input", "Audio escapes job directory")
    transcript = voice.transcribe(source, brief.language)
    try:
        return Brief.model_validate({**brief.model_dump(), "note_text": " ".join(s.text for s in transcript)})
    except ValidationError:
        raise AdLoomError("E_INPUT_INVALID", "input", "Transcribed explanation must be 1 to 200 characters") from None


def normalize(source: Path, output: Path) -> MediaInfo:
    if source.suffix.lower() not in {".mp4", ".mov"} or source.stat().st_size > 256*1024*1024:
        raise AdLoomError("E_INPUT_INVALID", "input", "Expected an MP4/MOV up to 256 MiB")
    info = probe(source)
    videos = [s for s in info["streams"] if s["codec_type"] == "video"]
    if len(videos) != 1 or "mov" not in info["format"]["format_name"].split(","):
        raise AdLoomError("E_INPUT_INVALID", "input", "Expected one video stream in an MP4/MOV")
    stream = videos[0]
    validate_duration(float(info["format"]["duration"]))
    if int(stream["width"])*int(stream["height"]) > 8_847_360 or max(int(stream["width"]), int(stream["height"])) > 4096:
        raise AdLoomError("E_INPUT_INVALID", "input", "Video geometry exceeds the local processing limit")
    fps = min(Fraction(stream["avg_frame_rate"]), Fraction(30))
    if fps <= 0:
        raise AdLoomError("E_INPUT_INVALID", "input", "Invalid frame rate")
    output.parent.mkdir(parents=True, exist_ok=True)
    has_audio = any(s["codec_type"] == "audio" for s in info["streams"])
    command = [
        "ffmpeg", "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
        "-i", str(source), "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"setpts=PTS-STARTPTS,fps={fps.numerator}/{fps.denominator},scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-threads", "1", "-filter_threads", "1", "-fflags", "+bitexact", "-flags:v", "+bitexact",
        "-map_metadata", "-1", "-t", "45",
    ]
    if has_audio:
        command += ["-af", "aresample=44100:async=1:first_pts=0", "-ac", "2", "-c:a", "aac", "-b:a", "128k"]
    try:
        subprocess.run([*command, str(output)], capture_output=True, timeout=180, check=True)
        result = probe(output)
        video = next(s for s in result["streams"] if s["codec_type"] == "video")
        count = int(video["nb_read_frames"])
        duration = count*1_000_000*fps.denominator//fps.numerator
        return MediaInfo(
            source_sha256=file_hash(source), normalized_sha256=file_hash(output),
            source_width=int(video["width"]), source_height=int(video["height"]),
            duration_us=duration, fps=FrameRate(numerator=fps.numerator, denominator=fps.denominator),
            frame_count=count, has_audio=has_audio,
        )
    except (subprocess.SubprocessError, ValidationError, ValueError, KeyError):
        raise AdLoomError("E_INPUT_INVALID", "input", "Video normalization failed") from None
