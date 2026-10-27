import importlib

import pytest

from adloom.adapters.mock_providers import MockMarketing
from adloom.config import AdLoomError
from adloom.jobs import JobStore
from adloom.schemas import Brief, FrameRate, MediaInfo


def test_publish_without_approval_never_calls_adapter(tmp_path):
    module = importlib.import_module("adloom.stages.publish")
    store = JobStore(tmp_path)
    head = store.create(
        Brief(
            video_path="input/source.mp4", note_text="샘플", region="서울", daily_budget_krw=10000
        ),
        MediaInfo(
            source_sha256="a" * 64,
            normalized_sha256="a" * 64,
            source_width=1920,
            source_height=1080,
            duration_us=10000000,
            fps=FrameRate(numerator=30, denominator=1),
            frame_count=300,
            has_audio=False,
        ),
    )
    adapter = MockMarketing()
    with pytest.raises(AdLoomError, match="E_APPROVAL_REQUIRED"):
        module.publish(store, head, adapter)
    assert adapter.requests == []


def prepared_job(tmp_path, rendered_case):
    import shutil

    module = importlib.import_module("adloom.stages.publish")
    root, snapshot = rendered_case
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(update={"publish_plan": module.fixture_publish_plan(snapshot)})
    for state in ("UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED", "AWAITING_APPROVAL"):
        head = store.transition(head, state, snapshot)
    return module, store, module.approve(store, head, "test-user")


def test_partial_publish_reuses_confirmed_ids(tmp_path, rendered_case):
    module, store, head = prepared_job(tmp_path, rendered_case)
    adapter = MockMarketing(fail_on=3)
    with pytest.raises(AdLoomError, match="E_PUBLISH_PARTIAL"):
        module.publish(store, head, adapter)
    failed = store.load(head.job_id)
    assert failed.state == "FAILED" and failed.failed_stage == "publish"
    completed = module.publish(store, failed, adapter)
    assert completed.state == "PUBLISHED_PAUSED"
    assert len({r["key"] for r in adapter.requests}) == len(adapter.requests)
    assert {r["resource"] for r in adapter.requests} == {
        "campaign",
        "adset",
        "image",
        "video",
        "creative",
        "ad",
    }
    for request in adapter.requests:
        if request["resource"] in {"campaign", "adset", "ad"}:
            assert request["payload"]["status"] == "PAUSED"
    count = len(adapter.requests)
    module.publish(store, completed, adapter)
    assert len(adapter.requests) == count


def test_asset_tamper_blocks_before_adapter(tmp_path, rendered_case):
    module, store, head = prepared_job(tmp_path, rendered_case)
    snapshot = store.snapshot(head)
    store.path(head.job_id, snapshot.variants[0].path).write_bytes(b"changed")
    adapter = MockMarketing()
    with pytest.raises(AdLoomError, match="E_APPROVAL_REQUIRED"):
        module.publish(store, head, adapter)
    assert adapter.requests == []


def test_ambiguous_request_is_not_replayed(tmp_path, rendered_case):
    module, store, head = prepared_job(tmp_path, rendered_case)

    class LostResponse:
        calls = 0

        def create(self, resource, payload, operation_key):
            self.calls += 1
            raise TimeoutError("response lost after remote create")

    adapter = LostResponse()
    with pytest.raises(AdLoomError, match="E_PUBLISH_PARTIAL"):
        module.publish(store, head, adapter)
    with pytest.raises(AdLoomError, match="E_PUBLISH_PARTIAL"):
        module.publish(store, store.load(head.job_id), adapter)
    assert adapter.calls == 1


def test_changed_copy_cannot_reuse_approval(tmp_path, rendered_case):
    module, store, head = prepared_job(tmp_path, rendered_case)
    snapshot = store.snapshot(head)
    changed = snapshot.understanding.model_copy(update={"primary_text": "변경된 본문"})
    head = store.commit(head, snapshot.model_copy(update={"understanding": changed}))
    adapter = MockMarketing()
    with pytest.raises(AdLoomError, match="E_APPROVAL_REQUIRED"):
        module.publish(store, head, adapter)
    assert adapter.requests == []
