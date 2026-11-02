import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adloom.config import Settings
from adloom.jobs import JobStore
from adloom.stages.publish import fixture_publish_plan
from adloom.web.app import create_app


def awaiting_job(tmp_path: Path, rendered_case) -> str:
    root, snapshot = rendered_case
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(update={"publish_plan": fixture_publish_plan(snapshot)})
    for state in ("UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED", "AWAITING_APPROVAL"):
        head = store.transition(head, state, snapshot)
    return head.job_id


@pytest.fixture
def client(tmp_path):
    return TestClient(
        create_app(Settings(data_dir=tmp_path)),
        base_url="http://127.0.0.1",
        headers={"X-AdLoom-Request": "1"},
    )


def test_page_and_status_report_fixture_mode(client):
    page = client.get("/")
    assert page.status_code == 200 and "AdLoom" in page.text
    status = client.get("/api/status").json()
    assert status["mode"] == "fixture" and status["live"] is False


def test_publish_without_approval_via_web_never_calls_marketing(client, tmp_path, rendered_case):
    job_id = awaiting_job(tmp_path, rendered_case)
    response = client.post(f"/api/jobs/{job_id}/publish")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "E_APPROVAL_REQUIRED"
    assert not any((tmp_path / "jobs" / job_id).glob("publish/*.json"))


def test_review_approve_publish_through_web(client, tmp_path, rendered_case):
    job_id = awaiting_job(tmp_path, rendered_case)
    review = client.get(f"/api/jobs/{job_id}").json()
    assert review["job"]["state"] == "AWAITING_APPROVAL"
    assert len(review["variants"]) == 6
    assert {"degraded", "policy_flags", "approval_issues"} <= review.keys()
    first = client.get(review["variants"][0]["url"])
    assert first.status_code == 200 and first.headers["content-type"] == "video/mp4"

    stale = client.post(f"/api/jobs/{job_id}/approve", json={"actor": "owner", "digest": "0" * 64})
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "E_REVISION_CONFLICT"

    approved = client.post(
        f"/api/jobs/{job_id}/approve",
        json={"actor": "owner", "digest": review["content_digest"]},
    )
    assert approved.status_code == 200 and approved.json()["state"] == "APPROVED"
    record = json.loads(
        (tmp_path / "jobs" / job_id / approved.json()["approval_ref"]["path"]).read_text()
    )
    assert record["channel"] == "web" and record["actor"] == "owner"

    published = client.post(f"/api/jobs/{job_id}/publish")
    assert published.status_code == 200 and published.json()["state"] == "PUBLISHED_PAUSED"
    log = client.get(f"/api/jobs/{job_id}").json()["operations"]
    assert log and all(op["phase"] == "CONFIRMED" for op in log)


@pytest.mark.parametrize(
    "relative", ["job.json", "../x/job.json", "renders/r000001/../../job.json"]
)
def test_file_route_serves_only_review_media(client, tmp_path, rendered_case, relative):
    job_id = awaiting_job(tmp_path, rendered_case)
    assert client.get(f"/api/jobs/{job_id}/files/{relative}").status_code in {404, 422}


def test_unknown_job_is_not_found(client):
    response = client.get(f"/api/jobs/{'a' * 32}")
    assert response.status_code == 404


def test_upload_rejects_non_video(client):
    response = client.post(
        "/api/jobs",
        data={"note": "note", "region": "Seoul", "budget": "10000"},
        files={"video": ("note.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_INPUT_INVALID"


@pytest.mark.parametrize(
    ("base_url", "headers"),
    [
        ("http://127.0.0.1", {}),
        ("http://127.0.0.1", {"X-AdLoom-Request": "1", "Origin": "https://evil.example"}),
        ("http://evil.example", {"X-AdLoom-Request": "1"}),
    ],
)
def test_cross_site_writes_are_refused_before_any_command(
    tmp_path, rendered_case, base_url, headers
):
    job_id = awaiting_job(tmp_path, rendered_case)
    review = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")
    digest = review.get(f"/api/jobs/{job_id}").json()["content_digest"]
    hostile = TestClient(create_app(Settings(data_dir=tmp_path)), base_url=base_url)
    response = hostile.post(
        f"/api/jobs/{job_id}/approve", json={"actor": "x", "digest": digest}, headers=headers
    )
    assert response.status_code == 403
    head = JobStore(tmp_path).load(job_id)
    assert head.state == "AWAITING_APPROVAL" and head.approval_ref is None


def test_missing_form_fields_use_error_envelope(client):
    response = client.post("/api/jobs", data={"note": "n"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "E_INPUT_INVALID"


def test_upload_runs_fixture_pipeline_and_removes_upload(client, tmp_path):
    with Path("tests/fixtures/sample.mp4").open("rb") as video:
        response = client.post(
            "/api/jobs",
            data={"note": "합성 샘플", "region": "서울", "budget": "10000"},
            files={"video": ("sample.mp4", video, "video/mp4")},
        )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "AWAITING_APPROVAL"
    assert not any((tmp_path / "uploads").glob("*"))
    jobs = client.get("/api/jobs").json()
    assert [job["job_id"] for job in jobs] == [response.json()["job_id"]]
