"""Live SAM 3.1 video tracking through Files + streamed Responses."""

import asyncio
import json
import re
import subprocess
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import httpx
from meta_sam_parser import (
    CompletedOutcome,
    InvalidSegmentationMaskError,
    ResponsesStreamError,
    ResponsesStreamEventError,
    ResponsesStreamFailedError,
    ResponsesStreamLaneError,
    ResponsesStreamParserError,
    ResponsesStreamRefusalError,
    ResponsesStreamSourceError,
    SegmentationBoxRecord,
    SegmentationMaskRecord,
    SegmentationTextRecord,
    VideoSegmentationResult,
    parse_responses_stream,
    video_segmentation_format,
)

from adloom.adapters.model_api import ModelApi, build_client, event_error, require_standard_model
from adloom.config import AdLoomError
from adloom.schemas import BBox, FrameRate, TrackResult

MODEL = "sam-3.1"
MAX_FRAMES = 1350
_MASK_HEADER = re.compile(r"data=(\d{1,12}),(\d{1,12}),")
_BOX_TOKEN = re.compile(r"<\|box;([^|]*)\|>")
_HEADER_CARRY = 40
_LANE_EVENTS = frozenset(
    {"response.output_text.delta", "response.output_text.done", "response.content_part.done"}
)


@dataclass(frozen=True)
class VideoGeometry:
    width: int
    height: int
    frame_count: int
    fps: Fraction


def probe_video(video: Path) -> VideoGeometry:
    try:
        output = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_streams",
                "-of",
                "json",
                str(video),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        ).stdout
        stream = json.loads(output)["streams"][0]
        geometry = VideoGeometry(
            width=int(stream["width"]),
            height=int(stream["height"]),
            frame_count=int(stream["nb_read_frames"]),
            fps=Fraction(stream["avg_frame_rate"]),
        )
    except (subprocess.SubprocessError, ValueError, KeyError, IndexError, ZeroDivisionError):
        raise AdLoomError("E_INPUT_INVALID", "track", "Video probe failed") from None
    if (
        min(geometry.width, geometry.height, geometry.frame_count) <= 0
        or geometry.frame_count > MAX_FRAMES
        or geometry.fps <= 0
    ):
        raise AdLoomError("E_INPUT_INVALID", "track", "Video geometry is outside product limits")
    return geometry


class _StreamWatch:
    """Observes the event source so a lane-less completed stream reads as zero matches."""

    def __init__(self, area: int) -> None:
        self.area = area
        self.lane_seen = False
        self.last_type: str | None = None
        self.terminal_event: dict[str, Any] | None = None
        self._carry = ""

    def observe(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        self.last_type = kind if isinstance(kind, str) else None
        if kind in _LANE_EVENTS:
            self.lane_seen = True
        if kind in ("response.failed", "error"):
            self.terminal_event = event
        text = event.get("delta") if kind == "response.output_text.delta" else None
        if isinstance(text, str):
            self._check_mask_headers(text)

    def _check_mask_headers(self, delta: str) -> None:
        # A header can be split across deltas, so keep a short tail of the previous text.
        window = self._carry + delta
        for match in _MASK_HEADER.finditer(window):
            if int(match.group(1)) * int(match.group(2)) > self.area:
                raise AdLoomError("E_RESOURCE_LIMIT", "track", "Mask exceeds the source frame")
        self._carry = window[-_HEADER_CARRY:]


def _run_coroutine[T](factory: Callable[[], Coroutine[Any, Any, T]]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())
    # Called from inside an event loop: run the parser loop on a private thread.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


def _unwrap(error: BaseException) -> BaseException:
    while isinstance(error, ResponsesStreamSourceError | ResponsesStreamParserError):
        if error.cause is None:
            break
        error = error.cause
    return error


class LiveTracking:
    """TrackingAdapter backed by ``sam-3.1`` with the official ``meta_sam_parser``."""

    def __init__(
        self, api_key: str, client: httpx.Client | None = None, model: str = MODEL
    ) -> None:
        self.model = require_standard_model(model, MODEL, "track")
        self.api = ModelApi(api_key, client or build_client())

    def request_body(self, file_id: str, prompt: str) -> dict[str, object]:
        return {
            "model": self.model,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_video", "file_id": file_id},
                    ],
                }
            ],
            "stream": True,
            "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
        }

    def track(self, video: Path, prompt: str) -> TrackResult:
        if not prompt.strip() or not prompt.isascii():
            raise AdLoomError("E_INPUT_INVALID", "track", "SAM prompt must be an ASCII noun phrase")
        geometry = probe_video(video)
        file_id = self.api.upload_file(video, "video/mp4", "track")
        body = self.request_body(file_id, prompt.strip())
        watch = _StreamWatch(geometry.width * geometry.height)
        with self.api.stream_events("/responses", body, "track", "SAM response") as events:
            result = self._parse(events, watch)
        return build_track(result, geometry)

    def cleanup(self) -> tuple[str, ...]:
        """Delete uploaded videos; return remote ids whose deletion failed."""
        return self.api.delete_uploads("track")

    @staticmethod
    def _parse(
        events: Iterator[dict[str, Any]], watch: _StreamWatch
    ) -> VideoSegmentationResult | None:
        async def source() -> AsyncIterator[dict[str, Any]]:
            for event in events:
                watch.observe(event)
                yield event

        async def consume() -> VideoSegmentationResult:
            return await parse_responses_stream(source(), video_segmentation_format()).final_result()

        try:
            return _run_coroutine(consume)
        except ResponsesStreamLaneError:
            if not watch.lane_seen and watch.last_type == "response.completed":
                # Documented zero-match: response.completed with no output_text lane.
                return None
            raise AdLoomError("E_API_SCHEMA", "track", "SAM stream lane is invalid") from None
        except ResponsesStreamRefusalError:
            raise AdLoomError("E_API_REFUSED", "track", "SAM refused the request") from None
        except (ResponsesStreamFailedError, ResponsesStreamEventError):
            raise event_error(watch.terminal_event, "track", "SAM response") from None
        except InvalidSegmentationMaskError:
            raise AdLoomError("E_API_SCHEMA", "track", "SAM returned an invalid mask") from None
        except ResponsesStreamError as error:
            cause = _unwrap(error)
            if isinstance(cause, AdLoomError):
                raise cause from None
            if isinstance(cause, MemoryError):
                raise AdLoomError("E_RESOURCE_LIMIT", "track", "SAM output is too large") from None
            raise AdLoomError("E_API_SCHEMA", "track", "SAM output could not be parsed") from None


def _check_frame_size(raw_output: str, geometry: VideoGeometry) -> None:
    """Every box token must report the probed source size as its w/h."""
    expected = (str(geometry.width), str(geometry.height))
    for match in _BOX_TOKEN.finditer(raw_output):
        fields = dict(
            part.split("=", 1) for part in match.group(1).split(";") if "=" in part
        )
        size = (fields.get("w", "").strip(), fields.get("h", "").strip())
        if size != expected:
            raise AdLoomError("E_API_SCHEMA", "track", "SAM frame size differs from the video")


def build_track(result: VideoSegmentationResult | None, geometry: VideoGeometry) -> TrackResult:
    """Pick the object seen on the most frames and lay its boxes out per frame."""
    boxes_by_object: dict[int, dict[int, BBox]] = {}
    if result is not None:
        if not isinstance(result.outcome, CompletedOutcome):
            raise AdLoomError("E_API_INCOMPLETE", "track", "SAM response is incomplete")
        if result.diagnostics:
            raise AdLoomError("E_API_SCHEMA", "track", "SAM output has protocol diagnostics")
        _check_frame_size(result.raw_output, geometry)
        for record in result.records:
            if isinstance(record, SegmentationTextRecord):
                if record.text.strip():
                    raise AdLoomError("E_API_SCHEMA", "track", "SAM output has unexpected text")
                continue
            if isinstance(record, SegmentationMaskRecord):
                continue
            _add_box(boxes_by_object, record, geometry)
    fps = FrameRate(numerator=geometry.fps.numerator, denominator=geometry.fps.denominator)
    if not boxes_by_object:
        return TrackResult(
            source_width=geometry.width,
            source_height=geometry.height,
            fps=fps,
            frame_count=geometry.frame_count,
            boxes=(None,) * geometry.frame_count,
            coverage=0.0,
        )
    chosen = min(boxes_by_object, key=lambda oid: (-len(boxes_by_object[oid]), oid))
    frames = boxes_by_object[chosen]
    return TrackResult(
        source_width=geometry.width,
        source_height=geometry.height,
        fps=fps,
        frame_count=geometry.frame_count,
        boxes=tuple(frames.get(index) for index in range(geometry.frame_count)),
        coverage=len(frames) / geometry.frame_count,
    )


def _add_box(
    boxes: dict[int, dict[int, BBox]], record: SegmentationBoxRecord, geometry: VideoGeometry
) -> None:
    if record.frame is None or not record.object_id.isdigit():
        raise AdLoomError("E_API_SCHEMA", "track", "SAM box lacks a frame or numeric object id")
    frame = record.frame.frame_index
    if not 0 <= frame < geometry.frame_count:
        raise AdLoomError("E_API_SCHEMA", "track", "SAM frame index is outside the video")
    # meta_sam_parser already returns half-open right/bottom; do not add 1.
    width, height = record.right - record.left, record.bottom - record.top
    if (
        record.left < 0
        or record.top < 0
        or width <= 0
        or height <= 0
        or record.right > geometry.width
        or record.bottom > geometry.height
    ):
        raise AdLoomError("E_API_SCHEMA", "track", "SAM box is outside the source frame")
    per_frame = boxes.setdefault(int(record.object_id), {})
    if frame in per_frame:
        raise AdLoomError("E_API_SCHEMA", "track", "SAM repeated an object on one frame")
    per_frame[frame] = BBox(
        x=record.left, y=record.top, w=width, h=height, score=record.confidence
    )
