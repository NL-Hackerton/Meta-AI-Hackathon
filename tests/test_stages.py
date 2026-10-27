import importlib
import json
from pathlib import Path

import pytest

from adloom.config import AdLoomError

FIXTURE = Path(
    "tests/fixtures/understanding/19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json"
)


class Replies:
    def __init__(self, always_bad=False):
        self.feedback = []
        self.always_bad = always_bad

    def understand(self, video, note_text, language, feedback=None):
        self.feedback.append(feedback)
        value = json.loads(FIXTURE.read_text())
        if len(self.feedback) == 1 or self.always_bad:
            value["hook_candidates"].append({"id": "extra", "text": "네 번째"})
        return json.dumps(value)


def test_schema_repair_is_one_attempt_with_feedback():
    stage = importlib.import_module("adloom.stages.understand")
    replies = Replies()
    result = stage.understand(Path("unused.mp4"), "설명", "ko", replies)
    assert len(result.hook_candidates) == 3
    assert replies.feedback[0] is None and "hook_candidates" in replies.feedback[1]
    bad = Replies(always_bad=True)
    with pytest.raises(AdLoomError, match="E_API_SCHEMA"):
        stage.understand(Path("unused.mp4"), "설명", "ko", bad)
    assert len(bad.feedback) == 2


def test_probe_rejects_sixty_seconds_before_processing():
    stage = importlib.import_module("adloom.stages.input")
    with pytest.raises(AdLoomError, match="E_INPUT_INVALID"):
        stage.validate_duration(60.0)


@pytest.mark.parametrize(
    "fragments, valid",
    [
        (("\u1100\u1161" * 200,), True),
        (("가" * 100, "나" * 100), False),
        ((), False),
    ],
)
def test_transcribed_note_normalization_and_combined_length(fragments, valid):
    stage = importlib.import_module("adloom.stages.input")
    from adloom.schemas import Brief, Segment

    class Voice:
        def transcribe(self, media, language):
            return tuple(
                Segment(start_us=i * 1000000, end_us=(i + 1) * 1000000, text=text)
                for i, text in enumerate(fragments)
            )

    brief = Brief(
        video_path="input/source.mp4",
        note_audio_path="input/note.wav",
        region="서울",
        daily_budget_krw=10000,
    )
    if valid:
        result = stage.fill_note(brief, Path("data"), Voice())
        assert result.note_text == "가" * 200
    else:
        with pytest.raises(AdLoomError, match="E_INPUT_INVALID"):
            stage.fill_note(brief, Path("data"), Voice())


def test_image_failure_preserves_real_frame_and_silent_video_has_no_subtitles(tmp_path):
    import subprocess

    from adloom.adapters.mock_providers import MockVoice
    from adloom.schemas import Understanding

    stage = importlib.import_module("adloom.stages.enrich")
    inputs = importlib.import_module("adloom.stages.input")
    source = tmp_path / "source.mp4"
    normalized = tmp_path / "normalized.mp4"
    subprocess.run(["bash", "tests/fixtures/make_sample.sh", str(source)], check=True)
    media = inputs.normalize(source, normalized)

    class BrokenImage:
        def generate_scene(self, prompt, size):
            raise AdLoomError("E_API_SCHEMA", "enrich", "injected failure")

    result = stage.enrich(
        normalized,
        media,
        Understanding.model_validate_json(FIXTURE.read_bytes()),
        tmp_path,
        BrokenImage(),
        MockVoice(tmp_path),
    )
    assert result.image_fallback and result.warnings
    assert not result.transcript
    from PIL import Image

    with Image.open(tmp_path / result.thumbnails[0].path) as image:
        assert image.size == (1080, 1920)
        assert image.getpixel((540, 960)) != image.getpixel((0, 0))
