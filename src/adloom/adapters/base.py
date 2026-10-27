from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from adloom.config import AdLoomError, Settings, load_config
from adloom.schemas import Segment, TrackResult


class PublishNotSent(AdLoomError):
    """The adapter guarantees no remote side effect occurred."""


class UnderstandingAdapter(Protocol):
    def understand(
        self, video: Path, note_text: str, language: str, feedback: str | None = None
    ) -> str: ...


class TrackingAdapter(Protocol):
    def track(self, video: Path, prompt: str) -> TrackResult: ...


class ImageAdapter(Protocol):
    def generate_scene(self, prompt: str, size: tuple[int, int]) -> Path: ...


class VoiceAdapter(Protocol):
    def transcribe(self, media: Path, language: str) -> tuple[Segment, ...]: ...


class MarketingPublisher(Protocol):
    def create(self, resource: str, payload: dict[str, object], operation_key: str) -> str: ...


@dataclass(frozen=True)
class Adapters:
    spark: UnderstandingAdapter
    sam: TrackingAdapter
    image: ImageAdapter
    voice: VoiceAdapter
    marketing: MarketingPublisher


def get_adapters(settings: Settings | None = None, job_dir: Path | None = None) -> Adapters:
    from adloom.adapters.mock_providers import (
        MockImage,
        MockMarketing,
        MockSpark,
        MockTracking,
        MockVoice,
    )

    config = settings or load_config()
    if config.mode != "fixture":
        raise AdLoomError("E_API_AUTH", "input", "Live adapters require human approval")
    fixtures = Path(__file__).resolve().parents[3] / "tests/fixtures"
    return Adapters(MockSpark(fixtures), MockTracking(), MockImage(job_dir or config.data_dir),
                    MockVoice(fixtures), MockMarketing())
