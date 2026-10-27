import importlib

import pytest

from adloom.schemas import BBox, FrameRate, TrackResult


def track(boxes):
    return TrackResult(source_width=1920, source_height=1080,
                       fps=FrameRate(numerator=30, denominator=1), frame_count=len(boxes),
                       boxes=tuple(boxes), coverage=sum(b is not None for b in boxes)/len(boxes))


def test_interpolation_and_missing_edges():
    crop = importlib.import_module("adloom.crop")
    left = BBox(x=800.0, y=400.0, w=100.0, h=100.0)
    right = BBox(x=840.0, y=420.0, w=120.0, h=100.0)
    values = crop.interpolate_boxes((None, left, None, right, None))
    assert values[0] == left and values[-1] == right
    assert (values[2].x, values[2].y, values[2].w) == (820.0, 410.0, 110.0)


@pytest.mark.parametrize("aspect", ["9:16", "4:5", "1:1"])
def test_feasible_crop_contains_box_with_margin(aspect):
    crop = importlib.import_module("adloom.crop")
    boxes = [BBox(x=800.0+i*2, y=400.0, w=100.0, h=100.0) for i in range(20)]
    plan = crop.plan_crops(track(boxes), aspect)
    for rect, box in zip(plan.rects, boxes, strict=True):
        assert rect.inside(1920, 1080)
        assert rect.x + rect.w * 0.06 <= box.x
        assert box.x + box.w <= rect.x + rect.w * 0.94
    assert not plan.clipped_frames


def test_low_coverage_and_infeasible_jump_are_explicit():
    crop = importlib.import_module("adloom.crop")
    center = BBox(x=800.0, y=400.0, w=100.0, h=100.0)
    degraded = crop.plan_crops(track([center, None, None, center, None]), "9:16")
    assert degraded.degraded
    assert len(set((r.x, r.y) for r in degraded.rects)) == 1
    jump = crop.plan_crops(track([center, BBox(x=1700.0, y=400.0, w=100.0, h=100.0)]), "9:16")
    assert jump.clipped_frames == (1,)
    assert abs(jump.rects[1].x-jump.rects[0].x) <= jump.max_step_px
