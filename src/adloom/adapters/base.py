import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from adloom.config import AdLoomError, Settings, load_config, require_live_ready
from adloom.schemas import Segment, Stage, TrackResult


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
    config = settings or load_config()
    if config.mode == "live":
        return _live_adapters(config, job_dir or config.data_dir)
    from adloom.adapters.mock_providers import (
        FIXTURE_FAULTS,
        MockImage,
        MockMarketing,
        MockSpark,
        MockTracking,
        MockVoice,
    )

    # Demo-only fault injection; read here so live runs never see it.
    fault = os.environ.get("ADLOOM_FIXTURE_FAULT", "").strip() or None
    if fault is not None and fault not in FIXTURE_FAULTS:
        raise AdLoomError(
            "E_INPUT_INVALID",
            "input",
            f"ADLOOM_FIXTURE_FAULT must be one of: {', '.join(sorted(FIXTURE_FAULTS))}",
        )
    fixtures = Path(__file__).resolve().parents[3] / "tests/fixtures"
    return Adapters(
        MockSpark(fixtures),
        MockTracking(),
        MockImage(job_dir or config.data_dir),
        MockVoice(fixtures),
        MockMarketing(fault=fault),
    )


def _live_adapters(config: Settings, job_dir: Path) -> Adapters:
    require_live_ready(config)
    assert config.model_api_key is not None and config.meta_access_token is not None
    assert config.meta_ad_account_id is not None and config.meta_page_id is not None
    assert config.meta_graph_version is not None
    # Imported lazily so fixture runs never load live clients.
    from adloom.adapters.image import LiveImage
    from adloom.adapters.marketing import LiveMarketing
    from adloom.adapters.sam import LiveTracking
    from adloom.adapters.spark import LiveSpark
    from adloom.adapters.voice import LiveVoice

    key = config.model_api_key
    return Adapters(
        LiveSpark(key, model=config.spark_model),
        LiveTracking(key),
        LiveImage(key, output=job_dir),
        LiveVoice(key, job_dir=job_dir),
        LiveMarketing(
            access_token=config.meta_access_token,
            account_id=config.meta_ad_account_id,
            page_id=config.meta_page_id,
            graph_version=config.meta_graph_version,
            job_dir=job_dir,
        ),
    )


def release_uploads(adapter: object, stage: Stage) -> tuple[str, ...]:
    """Delete an adapter's remote uploads; return warnings instead of raising.

    Adapters without remote files (fixtures) have no ``cleanup`` and need nothing.
    """
    cleanup = getattr(adapter, "cleanup", None)
    if cleanup is None:
        return ()
    try:
        leftover = tuple(cleanup())
    except Exception as error:  # cleanup must never replace the stage outcome
        return (f"{stage}: uploaded file cleanup failed ({type(error).__name__})",)
    return tuple(f"{stage}: uploaded file {file_id} could not be deleted" for file_id in leftover)
