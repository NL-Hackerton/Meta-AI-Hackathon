"""Deterministic, bounded crop planning in normalized source pixels."""

import math

from adloom.config import BBOX_MARGIN, MAX_STEP_PX, SAFE_BOTTOM, SAFE_TOP
from adloom.schemas import Aspect, BBox, CropPlan, Rect, TrackResult, resolution


def interpolate_boxes(boxes: tuple[BBox | None, ...]) -> tuple[BBox | None, ...]:
    known = [(index, box) for index, box in enumerate(boxes) if box is not None]
    if not known:
        return boxes
    result: list[BBox | None] = [known[0][1]] * len(boxes)
    for (start, left), (end, right) in zip(known, known[1:], strict=False):
        result[start] = left
        for i in range(start + 1, end):
            weight = (i - start) / (end - start)
            result[i] = BBox(
                x=left.x + (right.x - left.x) * weight,
                y=left.y + (right.y - left.y) * weight,
                w=left.w + (right.w - left.w) * weight,
                h=left.h + (right.h - left.h) * weight,
            )
    result[known[-1][0] :] = [known[-1][1]] * (len(boxes) - known[-1][0])
    return tuple(result)


def _position(target: float, low: float, high: float) -> float:
    return max(low, min(high, target))


def plan_crops(track: TrackResult, aspect: Aspect) -> CropPlan:
    output_w, output_h = resolution(aspect)
    scale = min(track.source_width / output_w, track.source_height / output_h)
    width = float(min(track.source_width // 2 * 2, round(output_w * scale / 2) * 2))
    height = float(min(track.source_height // 2 * 2, round(output_h * scale / 2) * 2))
    if width < 2 or height < 2:
        raise ValueError("source is too small for a chroma-aligned crop")
    center_x = (track.source_width - width) / 2
    center_y = (track.source_height - height) / 2
    previous_x, previous_y = center_x, center_y
    rects: list[Rect] = []
    clipped: list[int] = []
    unsafe: list[int] = []
    degraded = track.coverage < 0.6
    for index, box in enumerate(interpolate_boxes(track.boxes)):
        x, y = center_x, center_y
        if box is not None and not degraded:
            target_x, target_y = box.x + box.w / 2 - width / 2, box.y + box.h / 2 - height / 2
            target_x = target_x if not rects else previous_x + 0.15 * (target_x - previous_x)
            target_y = target_y if not rects else previous_y + 0.15 * (target_y - previous_y)
            low_x, high_x = 0.0, track.source_width - width
            low_y, high_y = 0.0, track.source_height - height
            if rects:
                low_x, high_x = (
                    max(low_x, previous_x - MAX_STEP_PX),
                    min(high_x, previous_x + MAX_STEP_PX),
                )
                low_y, high_y = (
                    max(low_y, previous_y - MAX_STEP_PX),
                    min(high_y, previous_y + MAX_STEP_PX),
                )
            margin = width * BBOX_MARGIN
            fit_x = (max(low_x, box.x + box.w + margin - width), min(high_x, box.x - margin))
            fit_y = (max(low_y, box.y + box.h + margin - height), min(high_y, box.y - margin))
            if math.ceil(fit_x[0] / 2) * 2 <= math.floor(fit_x[1] / 2) * 2:
                low_x, high_x = fit_x
            if math.ceil(fit_y[0] / 2) * 2 <= math.floor(fit_y[1] / 2) * 2:
                low_y, high_y = fit_y
            x = _position(
                round(target_x / 2) * 2, math.ceil(low_x / 2) * 2, math.floor(high_x / 2) * 2
            )
            y = _position(
                round(target_y / 2) * 2, math.ceil(low_y / 2) * 2, math.floor(high_y / 2) * 2
            )
        rect = Rect(x=float(x), y=float(y), w=width, h=height)
        if box is not None:
            margin = width * BBOX_MARGIN
            if not (
                x + margin <= box.x
                and box.x + box.w <= x + width - margin
                and y + margin <= box.y
                and box.y + box.h <= y + height - margin
            ):
                clipped.append(index)
            if aspect == "9:16" and not (
                y + height * SAFE_TOP <= box.y and box.y + box.h <= y + height * (1 - SAFE_BOTTOM)
            ):
                unsafe.append(index)
        rects.append(rect)
        previous_x, previous_y = x, y
    return CropPlan(
        aspect=aspect,
        source_width=track.source_width,
        source_height=track.source_height,
        frame_count=track.frame_count,
        max_step_px=MAX_STEP_PX,
        rects=tuple(rects),
        degraded=degraded,
        clipped_frames=tuple(clipped),
        safe_area_violation_frames=tuple(unsafe),
    )
