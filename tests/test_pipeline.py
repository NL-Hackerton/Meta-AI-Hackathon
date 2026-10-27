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
        result = subprocess.run([sys.executable, "-m", "adloom", *args], env=env, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    created = cli("run", "--video", "tests/fixtures/sample.mp4", "--note", "합성 샘플",
                  "--region", "서울", "--budget", "10000")
    assert created["state"] == "AWAITING_APPROVAL"
    job_id = created["job_id"]
    review = cli("inspect", job_id)
    assert len(review["snapshot"]["variants"]) == 6
    assert all((Path(tmp_path) / "jobs" / job_id / v["path"]).is_file() for v in review["snapshot"]["variants"])
    approved = cli("approve", job_id, "--actor", "test-user", "--digest", review["content_digest"])
    assert approved["state"] == "APPROVED"
    edited = cli("edit", job_id, "--hook-a", "수정한 문구")
    assert edited["state"] == "AWAITING_APPROVAL" and edited["revision"] == 2
    assert edited["approval_ref"] is None
    refused = subprocess.run([sys.executable, "-m", "adloom", "publish", job_id],
                             env=env, capture_output=True, text=True)
    assert refused.returncode == 1
    assert json.loads(refused.stderr)["error"]["code"] == "E_APPROVAL_REQUIRED"
    refreshed = cli("inspect", job_id)
    assert refreshed["content_digest"] != review["content_digest"]
    assert refreshed["snapshot"]["render_plan"]["hooks"][0]["text"] == "수정한 문구"
    cli("approve", job_id, "--actor", "test-user", "--digest", refreshed["content_digest"])
    published = cli("publish", job_id)
    assert published["state"] == "PUBLISHED_PAUSED"
    assert cli("inspect", job_id)["snapshot"]["publish_result"]["execution_mode"] == "fixture"
