import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adloom.adapters.mock_providers import MockMarketing
from adloom.config import Settings
from adloom.jobs import JobStore
from adloom.schemas import Moment
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


VOICE_SAMPLE = Path("tests/fixtures/voice/note-sample.wav")


def two_moment_job(tmp_path: Path, rendered_case) -> str:
    root, snapshot = rendered_case
    assert snapshot.understanding is not None
    moments = (
        Moment(start_us=0, end_us=3_000_000, reason="first"),
        Moment(start_us=4_000_000, end_us=7_000_000, reason="second"),
    )
    understanding = snapshot.understanding.model_copy(update={"key_moments": moments})
    snapshot = snapshot.model_copy(update={"understanding": understanding})
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(update={"publish_plan": fixture_publish_plan(snapshot)})
    for state in ("UNDERSTOOD", "TRACKED", "ENRICHED", "RENDERED", "AWAITING_APPROVAL"):
        head = store.transition(head, state, snapshot)
    return head.job_id


def approve_via_web(client, job_id: str) -> None:
    digest = client.get(f"/api/jobs/{job_id}").json()["content_digest"]
    response = client.post(f"/api/jobs/{job_id}/approve", json={"actor": "owner", "digest": digest})
    assert response.status_code == 200, response.text


def upload(client, files, note: str | None = None, **fields: str):
    with Path("tests/fixtures/sample.mp4").open("rb") as video:
        data = {"region": "서울", "budget": "10000", **fields}
        if note is not None:
            data["note"] = note
        return client.post(
            "/api/jobs", data=data, files={"video": ("sample.mp4", video, "video/mp4"), **files}
        )


def test_profile_round_trip_and_validation(client, tmp_path):
    assert client.get("/api/profile").json() == {"profile": None}
    profile = {
        "business_name": "Candle Studio",
        "category": "Home goods",
        "region": "Seoul",
        "daily_budget_krw": 10000,
        "destination_url": "https://example.com/shop",
        "language": "en",
    }
    saved = client.put("/api/profile", json=profile)
    assert saved.status_code == 200 and saved.json() == {"profile": profile}
    assert client.get("/api/profile").json() == {"profile": profile}
    assert json.loads((tmp_path / "profile.json").read_text()) == profile
    for change in (
        {"daily_budget_krw": 999},
        {"destination_url": "http://example.com"},
        {"language": "fr"},
        {"business_name": ""},
        {"business_name": "x" * 61},
        {"extra": 1},
    ):
        response = client.put("/api/profile", json={**profile, **change})
        assert response.status_code == 422, change
        assert response.json()["error"]["code"] == "E_INPUT_INVALID"
    assert client.get("/api/profile").json() == {"profile": profile}
    assert client.put("/api/profile", json={**profile, "destination_url": None}).status_code == 200


def test_status_reports_meta_and_key_presence_only(client, monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    status = client.get("/api/status").json()
    assert status["meta"]["connected"] is False
    assert status["meta"]["permissions"] == ["ads_management", "pages_read_engagement"]
    assert status["model_api"] == {"key_present": False}
    monkeypatch.setenv("MODEL_API_KEY", "secret-value")
    body = client.get("/api/status").text
    assert '"key_present":true' in body and "secret-value" not in body


def test_audio_only_upload_requires_review_then_confirm_runs(client, tmp_path):
    with VOICE_SAMPLE.open("rb") as audio:
        response = upload(client, {"note_audio": ("note.wav", audio, "audio/wav")})
    assert response.status_code == 200, response.text
    head = response.json()
    assert head["state"] == "CREATED" and head["note_status"] == "REVIEW_REQUIRED"
    job_id = head["job_id"]
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["note_proposal"] == "합성 샘플 음성 설명"
    assert detail["snapshot"]["brief"]["note_text"] is None
    kinds = {(n["job_id"], n["kind"]) for n in client.get("/api/notifications").json()}
    assert (job_id, "note_review") in kinds
    too_long = client.post(f"/api/jobs/{job_id}/confirm-note", json={"text": "x" * 201})
    assert too_long.status_code == 422
    confirmed = client.post(f"/api/jobs/{job_id}/confirm-note", json={"text": "합성 샘플"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "AWAITING_APPROVAL"
    assert confirmed.json()["note_status"] == "CONFIRMED"
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["snapshot"]["brief"]["note_text"] == "합성 샘플"
    again = client.post(f"/api/jobs/{job_id}/confirm-note", json={"text": "다시"})
    assert again.status_code == 409


def test_unknown_audio_fails_at_input_and_typed_note_recovers(client):
    response = upload(client, {"note_audio": ("note.webm", b"not a fixture", "audio/webm")})
    assert response.status_code == 200, response.text
    head = response.json()
    assert head["state"] == "FAILED" and head["failed_stage"] == "input"
    assert head["error"]["detail"] and head["note_status"] == "AUDIO_PENDING"
    notices = client.get("/api/notifications").json()
    assert [n["kind"] for n in notices] == ["note_review"]
    assert "fixture" not in notices[0]["detail"]
    confirmed = client.post(f"/api/jobs/{head['job_id']}/confirm-note", json={"text": "합성 샘플"})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["state"] == "AWAITING_APPROVAL"


def test_upload_requires_note_or_audio_and_audio_type(client):
    missing = upload(client, {})
    assert missing.status_code == 422
    wrong = upload(client, {"note_audio": ("note.txt", b"x", "text/plain")})
    assert wrong.status_code == 422


def test_detail_and_list_expose_source_moments_tracking_hooks(client, tmp_path, rendered_case):
    job_id = awaiting_job(tmp_path, rendered_case)
    detail = client.get(f"/api/jobs/{job_id}").json()
    source = client.get(detail["source_url"])
    assert source.status_code == 200 and source.headers["content-type"] == "video/mp4"
    assert client.get(f"/api/jobs/{job_id}/files/input/source.mp4").status_code == 404
    assert detail["note_proposal"] is None
    assert detail["moments"] == [
        {
            "index": 0,
            "start_us": 0,
            "end_us": 6_000_000,
            "reason": "합성 도형의 이동 구간",
            "selected": True,
        }
    ]
    tracking = detail["tracking"]
    frames = tracking["frame_count"]
    assert tracking["prompt"] == "gold square"
    assert len(tracking["boxes"]) == frames and tracking["boxes"][0] is None
    assert len(tracking["boxes"][1]) == 4
    assert set(tracking["crops"]) == {"9:16", "4:5", "1:1"}
    assert all(len(rects) == frames for rects in tracking["crops"].values())
    assert set(tracking["degraded"]) == {"9:16", "4:5", "1:1"}
    item = client.get("/api/jobs").json()[0]
    assert item["hooks"] == [{"id": "a", "text": "첫 문구"}, {"id": "b", "text": "둘째 문구"}]
    assert item["published_ads"] == [] and item["note_status"] == "CONFIRMED"


def test_edit_moments_and_product_rerender_and_stay_reversible(client, tmp_path, rendered_case):
    job_id = two_moment_job(tmp_path, rendered_case)
    approve_via_web(client, job_id)
    before = client.get(f"/api/jobs/{job_id}").json()
    assert [m["selected"] for m in before["moments"]] == [True, True]
    for body in ({"moments": []}, {"moments": [2]}, {"moments": [-1]}, {"product": ""}):
        assert client.post(f"/api/jobs/{job_id}/edit", json=body).status_code == 422, body
    edited = client.post(f"/api/jobs/{job_id}/edit", json={"moments": [1]})
    assert edited.status_code == 200, edited.text
    head = edited.json()
    assert head["revision"] == 2 and head["approval_ref"] is None
    assert head["state"] == "AWAITING_APPROVAL"
    after = client.get(f"/api/jobs/{job_id}").json()
    assert [m["selected"] for m in after["moments"]] == [False, True]
    assert after["content_digest"] != before["content_digest"]
    spans = after["snapshot"]["render_plan"]["timeline"]["spans"]
    assert spans[0]["source_start_us"] == 4_000_000
    assert all(
        v["url"].startswith(f"/api/jobs/{job_id}/files/renders/r000002/") for v in after["variants"]
    )
    restored = client.post(f"/api/jobs/{job_id}/edit", json={"moments": [0, 1]}).json()
    assert restored["revision"] == 3
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert [m["selected"] for m in detail["moments"]] == [True, True]
    assert detail["snapshot"]["render_plan"]["timeline"]["spans"][0]["source_start_us"] == 0
    product = client.post(f"/api/jobs/{job_id}/edit", json={"product": "red candle"})
    assert product.status_code == 200, product.text
    assert product.json()["revision"] == 4 and product.json()["state"] == "AWAITING_APPROVAL"
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["tracking"]["prompt"] == "red candle"
    assert detail["snapshot"]["understanding"]["sam_prompt"] == "gold square"


def test_abandon_unknown_publish_then_publish_refused_and_delete(
    client, tmp_path, rendered_case, monkeypatch
):
    job_id = awaiting_job(tmp_path, rendered_case)
    approve_via_web(client, job_id)

    def lost(self, resource, payload, operation_key):
        raise RuntimeError("connection dropped")

    monkeypatch.setattr(MockMarketing, "create", lost)
    failed = client.post(f"/api/jobs/{job_id}/publish")
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "E_PUBLISH_PARTIAL"
    monkeypatch.undo()
    operations = client.get(f"/api/jobs/{job_id}").json()["operations"]
    unknown = [op for op in operations if op["phase"] == "UNKNOWN"]
    assert len(unknown) == 1
    kinds = {n["kind"] for n in client.get("/api/notifications").json()}
    assert "unknown" in kinds
    assert client.delete(f"/api/jobs/{job_id}").status_code == 409
    resent = client.post(f"/api/jobs/{job_id}/publish")
    assert resent.status_code == 502 and resent.json()["error"]["code"] == "E_PUBLISH_PARTIAL"
    bad = client.post(
        f"/api/jobs/{job_id}/publish/abandon",
        json={"operation_key": "../job", "actor": "owner"},
    )
    assert bad.status_code in {404, 422}
    abandoned = client.post(
        f"/api/jobs/{job_id}/publish/abandon",
        json={"operation_key": unknown[0]["operation_key"], "actor": "owner"},
    )
    assert abandoned.status_code == 200, abandoned.text
    assert abandoned.json()["state"] == "FAILED"
    assert abandoned.json()["failed_stage"] == "publish"
    operation = client.get(f"/api/jobs/{job_id}").json()["operations"][0]
    assert operation["abandoned"] is True and operation["resolution_actor"] == "owner"
    refused = client.post(f"/api/jobs/{job_id}/publish")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "E_STATE_CONFLICT"
    assert client.post(f"/api/jobs/{job_id}/resume").status_code == 409
    deleted = client.delete(f"/api/jobs/{job_id}")
    assert deleted.status_code == 200 and deleted.json() == {"deleted": job_id}
    assert client.get(f"/api/jobs/{job_id}").status_code == 404
    assert not (tmp_path / "jobs" / job_id).exists()


def test_delete_refused_while_a_command_runs_and_requires_header(client, tmp_path, rendered_case):
    job_id = awaiting_job(tmp_path, rendered_case)
    plain = TestClient(create_app(Settings(data_dir=tmp_path)), base_url="http://127.0.0.1")
    assert plain.delete(f"/api/jobs/{job_id}").status_code == 403
    with JobStore(tmp_path).execution_lock():
        busy = client.delete(f"/api/jobs/{job_id}")
    assert busy.status_code == 409 and busy.json()["error"]["code"] == "E_JOB_BUSY"
    assert client.delete(f"/api/jobs/{job_id}").status_code == 200


def test_notifications_derive_ready_and_published(client, tmp_path, rendered_case):
    job_id = awaiting_job(tmp_path, rendered_case)
    ready = client.get("/api/notifications").json()
    assert [(n["job_id"], n["kind"]) for n in ready] == [(job_id, "ready")]
    assert {"id", "title", "detail", "at"} <= ready[0].keys()
    approve_via_web(client, job_id)
    assert client.post(f"/api/jobs/{job_id}/publish").status_code == 200
    published = client.get("/api/notifications").json()
    assert [n["kind"] for n in published] == ["published"]
    item = client.get("/api/jobs").json()[0]
    assert {ad["hook_id"] for ad in item["published_ads"]} == {h["id"] for h in item["hooks"]}
    assert all(
        ad["configured_status"] == "PAUSED" and ad["video_url"] for ad in item["published_ads"]
    )


def running_job(tmp_path: Path, rendered_case) -> str:
    root, snapshot = rendered_case
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(
        update={
            "publish_plan": fixture_publish_plan(snapshot),
            "variants": (),
            "render_plan": None,
        }
    )
    for state in ("UNDERSTOOD", "TRACKED", "ENRICHED"):
        head = store.transition(head, state, snapshot)
    store.commit(
        head, snapshot, run_state="RUNNING", active_run_id="f" * 32, pending_stage="assemble"
    )
    return head.job_id


def test_stale_running_job_reports_interrupted_and_resumes(client, tmp_path, rendered_case):
    job_id = running_job(tmp_path, rendered_case)
    assert client.get(f"/api/jobs/{job_id}").json()["job"]["run_state"] == "INTERRUPTED"
    assert client.get("/api/jobs").json()[0]["run_state"] == "INTERRUPTED"
    assert JobStore(tmp_path).load(job_id).run_state == "RUNNING"
    with JobStore(tmp_path).execution_lock():
        assert client.get(f"/api/jobs/{job_id}").json()["job"]["run_state"] == "RUNNING"
        assert client.get("/api/status").json()["busy"] is True
    assert client.get("/api/status").json()["busy"] is False
    resumed = client.post(f"/api/jobs/{job_id}/resume")
    assert resumed.status_code == 200, resumed.text
    head = resumed.json()
    assert head["state"] == "AWAITING_APPROVAL" and head["run_state"] == "IDLE"
    assert head["active_run_id"] is None and head["pending_stage"] is None


def test_publish_marks_job_running_until_it_finishes(client, tmp_path, rendered_case, monkeypatch):
    job_id = awaiting_job(tmp_path, rendered_case)
    approve_via_web(client, job_id)
    seen = []
    create = MockMarketing.create

    def observe(self, resource, payload, operation_key):
        head = JobStore(tmp_path).load(job_id)
        seen.append((head.run_state, head.pending_stage, head.active_run_id is not None))
        return create(self, resource, payload, operation_key)

    monkeypatch.setattr(MockMarketing, "create", observe)
    published = client.post(f"/api/jobs/{job_id}/publish").json()
    assert seen and set(seen) == {("RUNNING", "publish", True)}
    assert published["run_state"] == "IDLE" and published["active_run_id"] is None


def test_upload_language_is_recorded_and_validated(client):
    english = upload(client, {}, note="Synthetic sample", language="en")
    assert english.status_code == 200, english.text
    detail = client.get(f"/api/jobs/{english.json()['job_id']}").json()
    assert detail["snapshot"]["brief"]["language"] == "en"
    assert upload(client, {}, note="x", language="fr").status_code == 422


def test_rejected_video_leaves_no_orphan_job_folder(client, tmp_path):
    response = client.post(
        "/api/jobs",
        data={"note": "n", "region": "Seoul", "budget": "10000"},
        files={"video": ("clip.mp4", b"not a video", "video/mp4")},
    )
    assert response.status_code == 422
    assert list((tmp_path / "jobs").iterdir()) == []
    assert not any((tmp_path / "uploads").glob("*"))


def test_job_list_skips_jobs_deleted_mid_listing(client, tmp_path, rendered_case, monkeypatch):
    kept = awaiting_job(tmp_path, rendered_case)
    gone = awaiting_job(tmp_path, rendered_case)
    load = JobStore.load

    def racing(self, job_id):
        if job_id == gone:
            raise FileNotFoundError(job_id)
        return load(self, job_id)

    monkeypatch.setattr(JobStore, "load", racing)
    listed = client.get("/api/jobs")
    assert listed.status_code == 200
    assert [job["job_id"] for job in listed.json()] == [kept]
    assert client.get("/api/notifications").status_code == 200
