import importlib

import pytest

from adloom.config import AdLoomError
from adloom.schemas import Brief, MediaInfo


def test_job_storage_rejects_missing_artifacts_and_stale_commits(tmp_path):
    jobs = importlib.import_module("adloom.jobs")
    store = jobs.JobStore(tmp_path)
    media = MediaInfo.model_validate_json('{"source_sha256":"' + 'a' * 64 + '","normalized_sha256":"' + 'a' * 64 + '","source_width":1920,"source_height":1080,"duration_us":10000000,"fps":{"numerator":30,"denominator":1},"frame_count":300,"has_audio":false}')
    brief = Brief(video_path="input/source.mp4", note_text="컵", region="서울", daily_budget_krw=10000)
    head = store.create(brief, media)
    assert store.load(head.job_id) == head
    snapshot = store.snapshot(head)
    with pytest.raises(AdLoomError, match="E_STATE_CONFLICT"):
        store.transition(head, "TRACKED", snapshot)
    with pytest.raises(AdLoomError, match="E_STATE_CONFLICT"):
        store.transition(head, "UNDERSTOOD", snapshot)
    changed = store.commit(head, snapshot)
    with pytest.raises(AdLoomError, match="E_REVISION_CONFLICT"):
        store.commit(head, snapshot)
    assert store.load(head.job_id) == changed
    with pytest.raises(AdLoomError, match="E_INPUT_INVALID"):
        store.path("../escape")


def test_execution_lock_is_exclusive(tmp_path):
    jobs = importlib.import_module("adloom.jobs")
    with jobs.JobStore(tmp_path).execution_lock():
        with pytest.raises(AdLoomError, match="E_JOB_BUSY"):
            with jobs.JobStore(tmp_path).execution_lock():
                pytest.fail("second execution must not enter")


@pytest.mark.parametrize("source", [
    "CREATED", "UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED",
    "AWAITING_APPROVAL", "APPROVED", "PUBLISHED_PAUSED", "FAILED",
])
@pytest.mark.parametrize("target", [
    "CREATED", "UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED",
    "AWAITING_APPROVAL", "APPROVED", "PUBLISHED_PAUSED", "FAILED",
])
def test_closed_transition_table(source, target):
    jobs = importlib.import_module("adloom.jobs")
    forward = {
        ("CREATED", "UNDERSTOOD"), ("UNDERSTOOD", "TRACKED"),
        ("TRACKED", "ENRICHED"), ("ENRICHED", "RENDERED"),
        ("RENDERED", "AWAITING_APPROVAL"), ("AWAITING_APPROVAL", "APPROVED"),
        ("APPROVED", "PUBLISHED_PAUSED"),
        ("AWAITING_APPROVAL", "RENDERED"), ("APPROVED", "RENDERED"),
    }
    expected = (source, target) in forward or (target == "FAILED" and source != "FAILED")
    assert jobs.allowed_transition(source, target) == expected
