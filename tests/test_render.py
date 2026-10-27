import importlib

from adloom.schemas import FrameRate, MediaInfo, Moment, Segment


def test_timeline_pads_short_input_and_maps_subtitles():
    render = importlib.import_module("adloom.render")
    media = MediaInfo(
        source_sha256="a" * 64,
        normalized_sha256="b" * 64,
        source_width=1920,
        source_height=1080,
        duration_us=3000000,
        fps=FrameRate(numerator=30, denominator=1),
        frame_count=90,
        has_audio=True,
    )
    timeline = render.plan_timeline(
        media, (Moment(start_us=1000000, end_us=3000000, reason="test"),)
    )
    assert timeline.duration_us == 8000000
    segments = render.map_subtitles(
        timeline, (Segment(start_us=1500000, end_us=2500000, text="설명"),)
    )
    assert [(s.start_us, s.end_us) for s in segments] == [(500000, 1500000), (3500000, 4500000)]


def test_timeline_limits_body_to_twenty_eight_seconds():
    render = importlib.import_module("adloom.render")
    media = MediaInfo(
        source_sha256="a" * 64,
        normalized_sha256="b" * 64,
        source_width=1920,
        source_height=1080,
        duration_us=45000000,
        fps=FrameRate(numerator=30, denominator=1),
        frame_count=1350,
        has_audio=False,
    )
    timeline = render.plan_timeline(media, (Moment(start_us=0, end_us=45000000, reason="test"),))
    assert timeline.duration_us == 30000000
