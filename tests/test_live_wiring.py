"""Live wiring behind the still-closed gate. No request leaves the process."""

import hashlib
import json
import pickle
import sys
import types
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import httpx
import pytest
from PIL import Image

from adloom import pipeline
from adloom.adapters import base
from adloom.adapters.image import LiveImage
from adloom.adapters.sam import LiveTracking
from adloom.adapters.spark import LiveSpark
from adloom.adapters.voice import LiveVoice
from adloom.config import AdLoomError, Settings, live_settings_from_env, load_config
from adloom.jobs import JobStore, file_hash
from adloom.schemas import BBox, FrameRate, TrackResult
from adloom.stages.input import probe

SAMPLE = Path("tests/fixtures/sample.mp4")
UNDERSTANDING = Path(
    "tests/fixtures/understanding/"
    "19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json"
).read_text()
MODEL_KEY = "model-key-value-for-tests"
META_TOKEN = "meta-token-value-for-tests"
ENV = {
    "MODEL_API_KEY": MODEL_KEY,
    "META_ACCESS_TOKEN": META_TOKEN,
    "META_AD_ACCOUNT_ID": "act_1234567890",
    "META_PAGE_ID": "987654321",
    "META_GRAPH_VERSION": "v26.0",
    "ADLOOM_SPEND_LIMIT_USD": "5",
}


def live_settings(data_dir: Path, **changes: object) -> Settings:
    values: dict[str, object] = {
        "data_dir": data_dir,
        "mode": "live",
        "model_api_key": MODEL_KEY,
        "meta_access_token": META_TOKEN,
        "meta_ad_account_id": "act_1234567890",
        "meta_page_id": "987654321",
        "meta_graph_version": "v26.0",
        "spend_limit_usd": Decimal("5"),
    }
    values.update(changes)
    return Settings(**values)  # type: ignore[arg-type]


# --- config -------------------------------------------------------------------


def test_load_config_still_refuses_live():
    with pytest.raises(AdLoomError, match="E_API_AUTH"):
        load_config({**ENV, "ADLOOM_LIVE": "1"})


def test_live_settings_from_env_builds_live_settings(tmp_path):
    settings = live_settings_from_env({**ENV, "ADLOOM_DATA_DIR": str(tmp_path)})
    assert settings.mode == "live"
    assert settings.data_dir == tmp_path.resolve()
    assert settings.meta_ad_account_id == "act_1234567890"
    assert settings.meta_graph_version == "v26.0"
    assert settings.spend_limit_usd == Decimal("5")
    assert settings.model_api_key == MODEL_KEY and settings.meta_access_token == META_TOKEN


def test_live_settings_list_missing_names_never_values():
    env = {name: value for name, value in ENV.items() if name not in {"MODEL_API_KEY"}}
    env["META_PAGE_ID"] = "  "
    with pytest.raises(AdLoomError) as raised:
        live_settings_from_env(env)
    error = raised.value.error
    assert error.code == "E_API_AUTH"
    assert "MODEL_API_KEY" in error.detail and "META_PAGE_ID" in error.detail
    assert META_TOKEN not in error.detail and "act_1234567890" not in error.detail


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("META_AD_ACCOUNT_ID", "1234567890"),
        ("META_AD_ACCOUNT_ID", "act_12a"),
        ("META_PAGE_ID", "page-1"),
        ("META_GRAPH_VERSION", "26.0"),
        ("META_GRAPH_VERSION", "v26"),
        ("META_GRAPH_VERSION", "latest"),
        ("ADLOOM_SPEND_LIMIT_USD", "0"),
        ("ADLOOM_SPEND_LIMIT_USD", "lots"),
    ],
)
def test_live_settings_reject_malformed_values(name, value):
    with pytest.raises(AdLoomError) as raised:
        live_settings_from_env({**ENV, name: value})
    assert raised.value.error.code == "E_API_AUTH"
    assert name in raised.value.error.detail
    assert value not in raised.value.error.detail.replace(name, "")


def test_live_settings_refuse_contributor_model():
    with pytest.raises(AdLoomError, match="Standard Spark"):
        live_settings_from_env({**ENV, "ADLOOM_SPARK_MODEL": "muse-spark-1.3-contributor"})


def test_secrets_never_appear_in_repr_or_serialization(tmp_path):
    settings = live_settings_from_env({**ENV, "ADLOOM_DATA_DIR": str(tmp_path)})
    for text in (repr(settings), str(settings)):
        assert MODEL_KEY not in text and META_TOKEN not in text
    with pytest.raises(TypeError):
        pickle.dumps(settings)


# --- adapters -----------------------------------------------------------------


class LiveMarketingStub:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def create(self, resource: str, payload: dict[str, object], operation_key: str) -> str:
        raise AssertionError("not called")


def test_get_adapters_live_branch_builds_live_adapters(tmp_path, monkeypatch):
    seen: list[httpx.Request] = []

    def refuse(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise AssertionError("no request may be sent while wiring adapters")

    def offline_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(refuse))

    for module in ("spark", "sam", "image", "voice"):
        monkeypatch.setattr(f"adloom.adapters.{module}.build_client", offline_client)
    stub = types.ModuleType("adloom.adapters.marketing")
    stub.LiveMarketing = LiveMarketingStub  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "adloom.adapters.marketing", stub)

    adapters = base.get_adapters(live_settings(tmp_path), tmp_path / "job")
    assert isinstance(adapters.spark, LiveSpark)
    assert isinstance(adapters.sam, LiveTracking)
    assert isinstance(adapters.image, LiveImage)
    assert isinstance(adapters.voice, LiveVoice)
    assert isinstance(adapters.marketing, LiveMarketingStub)
    assert adapters.marketing.kwargs == {
        "access_token": META_TOKEN,
        "account_id": "act_1234567890",
        "page_id": "987654321",
        "graph_version": "v26.0",
        "job_dir": tmp_path / "job",
    }
    for adapter in (adapters.spark, adapters.sam, adapters.image, adapters.voice):
        assert isinstance(adapter.api.client._transport, httpx.MockTransport)  # type: ignore[attr-defined]
    assert adapters.image.output == tmp_path / "job"
    assert adapters.voice.job_dir == tmp_path / "job"
    assert seen == []


def test_get_adapters_live_requires_spending_limit(tmp_path):
    with pytest.raises(AdLoomError, match="Set a spending limit"):
        base.get_adapters(live_settings(tmp_path, spend_limit_usd=None), tmp_path)


def test_release_uploads_turns_failures_into_warnings():
    class Leftover:
        def cleanup(self) -> tuple[str, ...]:
            return ("file-1",)

    class Broken:
        def cleanup(self) -> tuple[str, ...]:
            raise RuntimeError("boom")

    assert base.release_uploads(object(), "track") == ()
    assert base.release_uploads(Leftover(), "track") == (
        "track: uploaded file file-1 could not be deleted",
    )
    assert base.release_uploads(Broken(), "understand") == (
        "understand: uploaded file cleanup failed (RuntimeError)",
    )


# --- full pipeline with in-process live fakes ---------------------------------


class FakeSpark:
    def __init__(self, leftover: tuple[str, ...] = ()) -> None:
        self.calls = 0
        self.cleanups = 0
        self.leftover = leftover

    def understand(
        self, video: Path, note_text: str, language: str, feedback: str | None = None
    ) -> str:
        self.calls += 1
        return UNDERSTANDING

    def cleanup(self) -> tuple[str, ...]:
        self.cleanups += 1
        return self.leftover


class FakeTracking:
    def __init__(self, fail: bool = False, broken_cleanup: bool = False) -> None:
        self.fail = fail
        self.broken_cleanup = broken_cleanup
        self.cleanups = 0

    def track(self, video: Path, prompt: str) -> TrackResult:
        if self.fail:
            raise AdLoomError("E_API_REMOTE", "track", "Injected tracking failure", True)
        stream = next(s for s in probe(video)["streams"] if s["codec_type"] == "video")
        width, height = int(stream["width"]), int(stream["height"])
        count = int(stream["nb_read_frames"])
        fps = Fraction(stream["avg_frame_rate"])
        box = BBox(x=width * 0.45, y=height * 0.4, w=width * 0.1, h=height * 0.15, score=0.9)
        return TrackResult(
            source_width=width,
            source_height=height,
            frame_count=count,
            fps=FrameRate(numerator=fps.numerator, denominator=fps.denominator),
            boxes=(box,) * count,
            coverage=1.0,
        )

    def cleanup(self) -> tuple[str, ...]:
        self.cleanups += 1
        if self.broken_cleanup:
            raise RuntimeError("delete failed")
        return ()


class FakeImage:
    def __init__(self, output: Path) -> None:
        self.output = output

    def generate_scene(self, prompt: str, size: tuple[int, int]) -> Path:
        path = self.output / "images" / f"{size[0]}x{size[1]}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (40, 80, 120)).save(path, format="PNG")
        return path


class FakeVoice:
    def transcribe(self, media: Path, language: str) -> tuple[()]:
        return ()


class FakeMarketing:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, object], str]] = []

    def create(self, resource: str, payload: dict[str, object], operation_key: str) -> str:
        self.requests.append((resource, payload, operation_key))
        return str(1000 + len(self.requests))


@pytest.fixture
def fakes(monkeypatch):
    built: dict[str, object] = {}

    def factory(spark=None, sam=None):
        built["spark"] = spark or FakeSpark()
        built["sam"] = sam or FakeTracking()
        built["marketing"] = FakeMarketing()

        def get_adapters(settings: Settings, job_dir: Path) -> base.Adapters:
            assert settings.mode == "live"
            return base.Adapters(
                built["spark"],  # type: ignore[arg-type]
                built["sam"],  # type: ignore[arg-type]
                FakeImage(job_dir),
                FakeVoice(),  # type: ignore[arg-type]
                built["marketing"],  # type: ignore[arg-type]
            )

        monkeypatch.setattr(pipeline, "get_adapters", get_adapters)
        return built

    return factory


def run_live(settings: Settings):
    return pipeline.run_file(
        settings, SAMPLE, "합성 샘플", "서울", 10000, destination="https://example.com/shop"
    )


def test_live_pipeline_records_live_mode_and_publishes_with_paths(tmp_path, fakes):
    built = fakes(spark=FakeSpark(leftover=("file-left",)))
    settings = live_settings(tmp_path)
    head = run_live(settings)
    assert head.state == "AWAITING_APPROVAL" and head.execution_mode == "live"
    assert built["spark"].cleanups == 1 and built["sam"].cleanups == 1
    review = pipeline.inspect_job(settings, head.job_id)
    snapshot = review["snapshot"]
    assert {p["mode"] for p in snapshot["provenance"]} == {"live"}
    assert {p["model"] for p in snapshot["provenance"]} == {
        "muse-spark-1.3",
        "sam-3.1",
        "muse-image-1.0",
    }
    assert {v["origin_mode"] for v in snapshot["variants"]} == {"live"}
    plan = snapshot["publish_plan"]
    assert (plan["execution_mode"], plan["account_id"], plan["page_id"]) == (
        "live",
        "1234567890",
        "987654321",
    )
    assert plan["graph_version"] == "v26.0"
    assert review["cleanup_warnings"] == [
        "understand: uploaded file file-left could not be deleted"
    ]
    assert review["notice"].startswith("Live mode")

    pipeline.approve_job(settings, head.job_id, "owner", review["content_digest"])
    published = pipeline.publish_job(settings, head.job_id)
    assert published.state == "PUBLISHED_PAUSED"
    root = JobStore(tmp_path).path(head.job_id)
    media = [(r, p) for r, p, _ in built["marketing"].requests if r in {"image", "video"}]
    assert [r for r, _ in media] == ["image", "video", "video"]
    for _, payload in media:
        assert set(payload) == {"sha256", "path"}
        assert file_hash(root / str(payload["path"])) == payload["sha256"]
    for operation in (root / "publish").glob("*.json"):
        assert ".live." in operation.name
    result = json.loads((root / "publish.json").read_bytes())
    assert result["execution_mode"] == "live"


def test_live_pipeline_cleans_up_when_tracking_fails(tmp_path, fakes):
    built = fakes(sam=FakeTracking(fail=True, broken_cleanup=True))
    settings = live_settings(tmp_path)
    with pytest.raises(AdLoomError, match="Injected tracking failure"):
        run_live(settings)
    (job,) = (tmp_path / "jobs").iterdir()
    head = JobStore(tmp_path).load(job.name)
    assert head.state == "FAILED" and head.failed_stage == "track"
    assert head.execution_mode == "live"
    assert built["spark"].cleanups == 1 and built["sam"].cleanups == 1
    warnings = pipeline.inspect_job(settings, job.name)["cleanup_warnings"]
    assert warnings == ["track: uploaded file cleanup failed (RuntimeError)"]


def test_live_run_requires_spending_limit_before_creating_a_job(tmp_path, fakes):
    fakes()
    with pytest.raises(AdLoomError, match="Set a spending limit") as raised:
        run_live(live_settings(tmp_path, spend_limit_usd=None))
    assert raised.value.error.code == "E_API_AUTH"
    assert not (tmp_path / "jobs").exists() or not any((tmp_path / "jobs").iterdir())


def test_fixture_and_live_jobs_never_mix(tmp_path, fakes):
    fixture_head = pipeline.run_file(
        Settings(data_dir=tmp_path), SAMPLE, "합성 샘플", "서울", 10000
    )
    assert fixture_head.execution_mode == "fixture"
    fakes()
    with pytest.raises(AdLoomError, match="E_STATE_CONFLICT"):
        pipeline.resume_job(live_settings(tmp_path), fixture_head.job_id)
    with pytest.raises(AdLoomError, match="E_STATE_CONFLICT"):
        pipeline.publish_job(live_settings(tmp_path), fixture_head.job_id)


def test_fixture_publish_payload_includes_path(tmp_path, rendered_case):
    from test_publish import prepared_job

    from adloom.adapters.mock_providers import MockMarketing

    module, store, head = prepared_job(tmp_path, rendered_case)
    adapter = MockMarketing()
    module.publish(store, head, adapter)
    media = [r["payload"] for r in adapter.requests if r["resource"] in {"image", "video"}]
    assert media and all(set(p) == {"sha256", "path"} for p in media)
    root = store.path(head.job_id)
    assert all(
        hashlib.sha256((root / str(p["path"])).read_bytes()).hexdigest() == p["sha256"]
        for p in media
    )


def test_get_adapters_live_branch_uses_real_live_marketing(tmp_path, monkeypatch):
    from adloom.adapters.marketing import LiveMarketing

    def offline_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(599)))

    for module in ("spark", "sam", "image", "voice"):
        monkeypatch.setattr(f"adloom.adapters.{module}.build_client", offline_client)
    marketing = base.get_adapters(live_settings(tmp_path), tmp_path).marketing
    assert isinstance(marketing, LiveMarketing)
    assert (marketing.account_id, marketing.page_id, marketing.graph_version) == (
        "act_1234567890",
        "987654321",
        "v26.0",
    )
    assert marketing.job_dir == tmp_path
    assert META_TOKEN not in repr(vars(marketing))
