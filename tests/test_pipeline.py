import importlib
import json
import os
import subprocess
import sys
from pathlib import Path


def test_cli_run_approve_publish(tmp_path):
    importlib.import_module("adloom.cli")
    env = {**os.environ, "ADLOOM_LIVE": "0", "ADLOOM_DATA_DIR": str(tmp_path)}

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "adloom", *args], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    created = cli(
        "run",
        "--video",
        "tests/fixtures/sample.mp4",
        "--note",
        "합성 샘플",
        "--region",
        "서울",
        "--budget",
        "10000",
    )
    assert created["state"] == "AWAITING_APPROVAL"
    job_id = created["job_id"]
    review = cli("inspect", job_id)
    assert len(review["snapshot"]["variants"]) == 6
    assert all(
        (Path(tmp_path) / "jobs" / job_id / v["path"]).is_file()
        for v in review["snapshot"]["variants"]
    )
    approved = cli("approve", job_id, "--actor", "test-user", "--digest", review["content_digest"])
    assert approved["state"] == "APPROVED"
    edited = cli("edit", job_id, "--hook-a", "수정한 문구")
    assert edited["state"] == "AWAITING_APPROVAL" and edited["revision"] == 2
    assert edited["approval_ref"] is None
    refused = subprocess.run(
        [sys.executable, "-m", "adloom", "publish", job_id], env=env, capture_output=True, text=True
    )
    assert refused.returncode == 1
    assert json.loads(refused.stderr)["error"]["code"] == "E_APPROVAL_REQUIRED"
    refreshed = cli("inspect", job_id)
    assert refreshed["content_digest"] != review["content_digest"]
    assert refreshed["snapshot"]["render_plan"]["hooks"][0]["text"] == "수정한 문구"
    cli("approve", job_id, "--actor", "test-user", "--digest", refreshed["content_digest"])
    published = cli("publish", job_id)
    assert published["state"] == "PUBLISHED_PAUSED"
    assert cli("inspect", job_id)["snapshot"]["publish_result"]["execution_mode"] == "fixture"


def test_edit_refreshes_policy_for_review_and_approval(tmp_path, rendered_case):
    from test_publish import prepared_job

    from adloom.config import Settings
    from adloom.pipeline import edit_job, inspect_job

    _, _, head = prepared_job(tmp_path, rendered_case)
    settings = Settings(data_dir=tmp_path)
    edit_job(settings, head.job_id, primary_text="100% 보장")
    blocked = inspect_job(settings, head.job_id)
    assert blocked["snapshot"]["understanding"]["policy_flags"][0]["severity"] == "block"
    assert blocked["approval_issues"] == ["policy_block"]
    edit_job(settings, head.job_id, primary_text="제품 정보를 확인하세요")
    corrected = inspect_job(settings, head.job_id)
    assert corrected["snapshot"]["understanding"]["policy_flags"] == []
    assert corrected["approval_issues"] == []


def test_cli_audio_note_stops_for_review_until_confirmed(tmp_path):
    env = {**os.environ, "ADLOOM_LIVE": "0", "ADLOOM_DATA_DIR": str(tmp_path)}

    def cli(*args):
        result = subprocess.run(
            [sys.executable, "-m", "adloom", *args], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    created = cli(
        "run",
        "--video",
        "tests/fixtures/sample.mp4",
        "--note-audio",
        "tests/fixtures/voice/note-sample.wav",
        "--region",
        "서울",
        "--budget",
        "10000",
    )
    assert created["state"] == "CREATED" and created["note_status"] == "REVIEW_REQUIRED"
    review = cli("inspect", created["job_id"])
    assert review["snapshot"]["note_proposal"] == "합성 샘플 음성 설명"
    assert review["snapshot"]["brief"]["note_audio_path"] == "input/note.wav"
    assert cli("resume", created["job_id"])["state"] == "CREATED"
    confirmed = cli("confirm-note", created["job_id"], "--text", "합성 샘플 음성 설명")
    assert confirmed["state"] == "AWAITING_APPROVAL" and confirmed["note_status"] == "CONFIRMED"


def test_pipeline_marks_run_state_while_stages_execute(tmp_path, monkeypatch):
    from adloom.adapters.mock_providers import MockTracking
    from adloom.config import Settings
    from adloom.jobs import JobStore
    from adloom.pipeline import run_file

    seen = []
    track = MockTracking.track

    def observe(self, video, prompt):
        store = JobStore(tmp_path)
        (path,) = (tmp_path / "jobs").glob("*/job.json")
        head = store.load(path.parent.name)
        seen.append((head.run_state, head.pending_stage, head.active_run_id is not None))
        seen.append(store.busy())
        return track(self, video, prompt)

    monkeypatch.setattr(MockTracking, "track", observe)
    head = run_file(
        Settings(data_dir=tmp_path), Path("tests/fixtures/sample.mp4"), "합성 샘플", "서울", 10000
    )
    assert seen == [("RUNNING", "track", True), True]
    assert head.state == "AWAITING_APPROVAL" and head.run_state == "IDLE"
    assert head.active_run_id is None and head.pending_stage is None
    assert JobStore(tmp_path).busy() is False
