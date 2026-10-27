from pathlib import Path

from adloom.adapters.base import TrackingAdapter
from adloom.config import ASPECTS
from adloom.crop import plan_crops
from adloom.schemas import CropPlan, TrackResult


def track(video: Path, prompt: str, adapter: TrackingAdapter) -> tuple[TrackResult, tuple[CropPlan, ...]]:
    result = adapter.track(video, prompt)
    return result, tuple(plan_crops(result, aspect) for aspect in ASPECTS)
