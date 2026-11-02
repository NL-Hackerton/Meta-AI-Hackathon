from pathlib import Path

from adloom.adapters.base import TrackingAdapter, release_uploads
from adloom.config import ASPECTS
from adloom.crop import plan_crops
from adloom.schemas import CropPlan, TrackResult


def track(
    video: Path, prompt: str, adapter: TrackingAdapter, warnings: list[str] | None = None
) -> tuple[TrackResult, tuple[CropPlan, ...]]:
    """Track the product; uploaded files are released whether tracking succeeds or not."""
    try:
        result = adapter.track(video, prompt)
    finally:
        leftover = release_uploads(adapter, "track")
        if warnings is not None:
            warnings.extend(leftover)
    return result, tuple(plan_crops(result, aspect) for aspect in ASPECTS)
