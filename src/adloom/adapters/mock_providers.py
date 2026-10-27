"""Synthetic fixtures, not model inference or real advertising resources."""

import hashlib
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw
from pydantic import TypeAdapter

from adloom.adapters.base import PublishNotSent
from adloom.config import AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import BBox, FrameRate, Segment, TrackResult


class MockSpark:
    def __init__(self, fixtures: Path) -> None:
        self.fixtures = fixtures

    def understand(
        self, video: Path, note_text: str, language: str, feedback: str | None = None
    ) -> str:
        fixture = self.fixtures / "understanding" / f"{file_hash(video)}.json"
        if not fixture.is_file():
            raise AdLoomError("E_API_SCHEMA", "understand", "No fixture for this video digest")
        return fixture.read_text()


class MockTracking:
    def track(self, video: Path, prompt: str) -> TrackResult:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-count_frames",
                "-show_streams",
                "-of",
                "json",
                str(video),
            ],
            timeout=60,
        )
        stream = json.loads(output)["streams"][0]
        width, height, count = (
            int(stream["width"]),
            int(stream["height"]),
            int(stream["nb_read_frames"]),
        )
        fps = Fraction(stream["avg_frame_rate"])
        boxes: list[BBox | None] = []
        for index in range(count):
            t = index / float(fps)
            boxes.append(
                None
                if index % 13 == 0
                else BBox(
                    x=width * (880 + 180 * math.sin(t * 0.6)) / 1920,
                    y=height * (460 + 80 * math.sin(t * 0.4)) / 1080,
                    w=width * 160 / 1920,
                    h=height * 160 / 1080,
                    score=1.0,
                )
            )
        return TrackResult(
            source_width=width,
            source_height=height,
            frame_count=count,
            fps=FrameRate(numerator=fps.numerator, denominator=fps.denominator),
            boxes=tuple(boxes),
            coverage=sum(b is not None for b in boxes) / count,
        )


class MockImage:
    def __init__(self, output: Path) -> None:
        self.output = output

    def generate_scene(self, prompt: str, size: tuple[int, int]) -> Path:
        digest = hashlib.sha256(f"{prompt}:{size}".encode()).hexdigest()
        path = self.output / "images" / f"{digest}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", size)
        draw = ImageDraw.Draw(image)
        for y in range(size[1]):
            draw.line((0, y, size[0], y), fill=(18, 40 + int(35 * y / size[1]), 38))
        image.save(path, format="PNG")
        return path


class MockVoice:
    def __init__(self, fixtures: Path) -> None:
        self.fixtures = fixtures

    def transcribe(self, media: Path, language: str) -> tuple[Segment, ...]:
        path = self.fixtures / "voice" / f"{file_hash(media)}.json"
        if not path.is_file():
            raise AdLoomError("E_API_SCHEMA", "input", "No transcription fixture for this digest")
        return TypeAdapter(tuple[Segment, ...]).validate_json(path.read_bytes())


class MockMarketing:
    def __init__(self, fail_on: int | None = None) -> None:
        self.requests: list[dict[str, object]] = []
        self.fail_on = fail_on

    def create(self, resource: str, payload: dict[str, object], operation_key: str) -> str:
        if resource not in {"video", "image", "creative", "campaign", "adset", "ad"}:
            raise AdLoomError("E_INPUT_INVALID", "publish", "Unknown resource")
        if resource in {"campaign", "adset", "ad"} and payload.get("status") != "PAUSED":
            raise AdLoomError("E_INPUT_INVALID", "publish", "Advertising resources must be paused")
        if self.fail_on == len(self.requests) + 1:
            self.fail_on = None
            raise PublishNotSent(
                "E_PUBLISH_PARTIAL", "publish", "Injected pre-request failure", True
            )
        self.requests.append({"resource": resource, "payload": payload, "key": operation_key})
        return "fixture-" + hashlib.sha256(operation_key.encode()).hexdigest()[:24]
