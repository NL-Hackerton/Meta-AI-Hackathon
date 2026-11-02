"""English output path and the fixture publish fault used for the recovery demo."""

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from adloom.adapters import mock_providers
from adloom.adapters.base import get_adapters
from adloom.adapters.mock_providers import MockImage
from adloom.config import FONT_PATH, AdLoomError, Settings
from adloom.jobs import JobStore
from adloom.schemas import Segment, Understanding
from adloom.stages import publish as publish_stage
from adloom.stages.enrich import cta_label, enrich, wrap_lines
from adloom.stages.input import normalize

FIXTURE = Path(
    "tests/fixtures/understanding/19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json"
)


def test_cta_label_follows_language():
    assert cta_label("LEARN_MORE", "ko") == "자세히 보기"
    assert cta_label("LEARN_MORE", "en") == "Learn more"
    with pytest.raises(AdLoomError, match="E_INPUT_INVALID"):
        cta_label("LEARN_MORE", "fr")


def test_wrap_keeps_english_words_whole_and_korean_unchanged():
    image = Image.new("RGBA", (400, 400))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT_PATH), 58)
    lines = wrap_lines(draw, font, "Fresh bread every single morning", 400)
    assert len(lines) > 1
    assert all(
        word in "Fresh bread every single morning".split()
        for line in lines
        for word in line.split()
    )
    assert " ".join(line.strip() for line in lines) == "Fresh bread every single morning"
    korean = "매일 아침 갓 구운 빵을 만나보세요"
    lines = wrap_lines(draw, font, korean, 400)
    assert "".join(lines) == korean
    assert len(lines) > 1


class RecordingVoice:
    def __init__(self) -> None:
        self.languages: list[str] = []

    def transcribe(self, media: Path, language: str) -> tuple[Segment, ...]:
        self.languages.append(language)
        return ()


@pytest.fixture(scope="module")
def normalized_sample(tmp_path_factory):
    root = tmp_path_factory.mktemp("sample")
    source = root / "source.mp4"
    subprocess.run(["bash", "tests/fixtures/make_sample.sh", str(source)], check=True)
    normalized = root / "normalized.mp4"
    return normalized, normalize(source, normalized)


def test_endcard_and_voice_follow_brief_language(tmp_path, normalized_sample):
    normalized, media = normalized_sample
    media = media.model_copy(update={"has_audio": True})
    understanding = Understanding.model_validate_json(FIXTURE.read_bytes())
    hashes = {}
    for language in ("ko", "en"):
        job = tmp_path / language
        voice = RecordingVoice()
        result = enrich(
            normalized, media, understanding, job, MockImage(job), voice, language=language
        )
        assert voice.languages == [language]
        hashes[language] = [card.sha256 for card in result.endcards]
    assert all(ko != en for ko, en in zip(hashes["ko"], hashes["en"], strict=True))
    default = enrich(
        normalized,
        media,
        understanding,
        tmp_path / "default",
        MockImage(tmp_path / "default"),
        RecordingVoice(),
    )
    assert [card.sha256 for card in default.endcards] == hashes["ko"]


def approved_job(tmp_path, rendered_case):
    root, snapshot = rendered_case
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(
        update={"publish_plan": publish_stage.fixture_publish_plan(snapshot)}
    )
    for state in ("UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED", "AWAITING_APPROVAL"):
        head = store.transition(head, state, snapshot)
    return store, publish_stage.approve(store, head, "test-user")


def test_fixture_fault_is_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("ADLOOM_FIXTURE_FAULT", raising=False)
    assert get_adapters(Settings(data_dir=tmp_path)).marketing.fault is None  # type: ignore[attr-defined]


def test_unknown_fixture_fault_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("ADLOOM_FIXTURE_FAULT", "explode")
    with pytest.raises(AdLoomError, match="ADLOOM_FIXTURE_FAULT"):
        get_adapters(Settings(data_dir=tmp_path))


def test_publish_unknown_once_journals_unknown_and_refuses_resend(
    tmp_path, rendered_case, monkeypatch
):
    monkeypatch.setattr(mock_providers, "_FIRED_FAULTS", set())
    monkeypatch.setenv("ADLOOM_FIXTURE_FAULT", "publish_unknown_once")
    store, head = approved_job(tmp_path, rendered_case)
    settings = Settings(data_dir=tmp_path)
    first = get_adapters(settings, store.path(head.job_id)).marketing
    with pytest.raises(AdLoomError, match="E_PUBLISH_PARTIAL"):
        publish_stage.publish(store, head, first)
    operations = publish_stage.operations(store, head.job_id)
    unknown = [op for op in operations if op.phase == "UNKNOWN"]
    assert [op.resource_kind for op in unknown] == ["adset"]
    failed = store.load(head.job_id)
    assert failed.state == "FAILED" and failed.failed_stage == "publish"

    # A fresh adapter in the same process no longer injects, yet the journal still refuses.
    second = get_adapters(settings, store.path(head.job_id)).marketing
    with pytest.raises(AdLoomError, match="do not resend"):
        publish_stage.publish(store, failed, second)
    assert not any(r["resource"] == "adset" for r in second.requests)  # type: ignore[attr-defined]
    assert [
        op.phase
        for op in publish_stage.operations(store, head.job_id)
        if op.resource_kind == "adset"
    ] == ["UNKNOWN"]
