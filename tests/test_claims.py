"""Owner review of the factual claims Spark found in the ad copy."""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from adloom.config import AdLoomError, Settings
from adloom.jobs import JobStore
from adloom.pipeline import edit_job, review_claims
from adloom.schemas import ClaimCandidate, NoteDocument, NoteEvidence, VideoEvidence
from adloom.stages.publish import fixture_publish_plan
from adloom.web.app import create_app


def claims_job(tmp_path: Path, rendered_case, *, broken_quote: bool = False) -> str:
    """A rendered job whose understanding carries claims, as live Spark output would."""
    root, snapshot = rendered_case
    assert snapshot.understanding is not None and snapshot.brief.note_text
    note = NoteDocument(text=snapshot.brief.note_text)
    quote = "다른" if broken_quote else note.text[0:2]
    claims = (
        ClaimCandidate(
            id="origin",
            text="Made from a synthetic sample",
            classification="explicit",
            references=(NoteEvidence(source_digest=note.sha256, start=0, end=2, quote=quote),),
        ),
        ClaimCandidate(
            id="gold",
            text="The square is gold",
            classification="observation",
            references=(
                VideoEvidence(
                    source_digest=snapshot.media.normalized_sha256,
                    start_us=1_000_000,
                    end_us=2_500_000,
                ),
            ),
        ),
        ClaimCandidate(id="gift", text="A good gift", classification="inference"),
    )
    understanding = snapshot.understanding.model_copy(update={"claims": claims})
    store = JobStore(tmp_path)
    head = store.create(snapshot.brief, snapshot.media)
    shutil.copytree(root, store.path(head.job_id), dirs_exist_ok=True)
    snapshot = snapshot.model_copy(update={"understanding": understanding})
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


def review(client, job_id: str, decisions: dict[str, str], actor: str = "owner"):
    return client.post(f"/api/jobs/{job_id}/claims", json={"actor": actor, "decisions": decisions})


def approve(client, job_id: str, digest: str):
    return client.post(f"/api/jobs/{job_id}/approve", json={"actor": "owner", "digest": digest})


def test_pending_claims_are_listed_with_evidence_and_block_approval(
    client, tmp_path, rendered_case
):
    job_id = claims_job(tmp_path, rendered_case)
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert "approval_error" not in detail
    claims = {claim["id"]: claim for claim in detail["claims"]}
    assert list(claims) == ["origin", "gold", "gift"]
    origin, gold, gift = claims["origin"], claims["gold"], claims["gift"]
    assert origin["required"] and gold["required"] and not gift["required"]
    assert origin["status"] == "pending" and origin["actor"] is None
    assert origin["evidence"] == [
        {
            "id": "origin#1",
            "kind": "note",
            "quote": "합성",
            "start": 0,
            "end": 2,
            "valid": True,
            "reason": None,
        }
    ]
    assert gold["evidence"] == [
        {
            "id": "gold#1",
            "kind": "video",
            "start_us": 1_000_000,
            "end_us": 2_500_000,
            "valid": True,
            "reason": None,
        }
    ]
    assert origin["issues"] == ["unreviewed_claim"] and gift["issues"] == []
    assert "unreviewed_claim:origin" in detail["approval_issues"]
    blocked = approve(client, job_id, detail["content_digest"])
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "E_POLICY_BLOCK"


def test_accepting_required_claims_makes_the_job_approvable(client, tmp_path, rendered_case):
    job_id = claims_job(tmp_path, rendered_case)
    before = client.get(f"/api/jobs/{job_id}").json()
    response = review(client, job_id, {"origin": "accepted", "gold": "accepted"})
    assert response.status_code == 200, response.text
    head = response.json()
    assert head["revision"] == before["job"]["revision"]
    assert head["manifest_seq"] == before["job"]["manifest_seq"] + 1
    assert head["state"] == "AWAITING_APPROVAL"
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["approval_issues"] == []
    claims = {claim["id"]: claim for claim in detail["claims"]}
    assert claims["origin"]["status"] == "accepted" and claims["origin"]["actor"] == "owner"
    assert claims["gift"]["status"] == "pending"
    assert detail["content_digest"] != before["content_digest"]
    # Repeating the same decisions is a no-op: no new manifest, same digest.
    again = review(client, job_id, {"origin": "accepted"}).json()
    assert again["manifest_seq"] == head["manifest_seq"]
    approved = approve(client, job_id, detail["content_digest"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["state"] == "APPROVED"


def test_review_after_approval_invalidates_it(client, tmp_path, rendered_case):
    job_id = claims_job(tmp_path, rendered_case)
    review(client, job_id, {"origin": "accepted", "gold": "accepted"})
    digest = client.get(f"/api/jobs/{job_id}").json()["content_digest"]
    assert approve(client, job_id, digest).status_code == 200
    changed = review(client, job_id, {"gift": "accepted"})
    assert changed.status_code == 200, changed.text
    head = changed.json()
    assert head["state"] == "AWAITING_APPROVAL" and head["approval_ref"] is None
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["approval"] is None and detail["content_digest"] != digest
    stale = approve(client, job_id, digest)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "E_REVISION_CONFLICT"
    assert client.post(f"/api/jobs/{job_id}/publish").status_code == 409
    assert approve(client, job_id, detail["content_digest"]).status_code == 200


def test_rejected_claim_blocks_until_the_copy_is_edited(client, tmp_path, rendered_case):
    job_id = claims_job(tmp_path, rendered_case)
    review(client, job_id, {"origin": "accepted", "gold": "accepted", "gift": "rejected"})
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert detail["approval_issues"] == ["rejected_claim:gift"]
    gift = next(claim for claim in detail["claims"] if claim["id"] == "gift")
    assert gift["status"] == "rejected" and gift["issues"] == ["rejected_claim"]
    assert approve(client, job_id, detail["content_digest"]).status_code == 409
    # Rewriting the headline is a copy change: the rejected claim leaves the review.
    settings = Settings(data_dir=tmp_path)
    head = edit_job(settings, job_id, headline="Gold square")
    assert head.state == "AWAITING_APPROVAL" and head.revision == 2
    detail = client.get(f"/api/jobs/{job_id}").json()
    assert [claim["id"] for claim in detail["claims"]] == ["origin", "gold"]
    assert all(claim["status"] == "accepted" for claim in detail["claims"])
    assert detail["approval_issues"] == []
    assert approve(client, job_id, detail["content_digest"]).status_code == 200


def test_non_copy_edit_keeps_a_rejected_claim(tmp_path, rendered_case):
    job_id = claims_job(tmp_path, rendered_case)
    settings = Settings(data_dir=tmp_path)
    review_claims(settings, job_id, {"gift": "rejected"}, "owner")
    edit_job(settings, job_id, product="red candle")
    store = JobStore(tmp_path)
    snapshot = store.snapshot(store.load(job_id))
    assert snapshot.understanding is not None
    assert [claim.id for claim in snapshot.understanding.claims] == ["origin", "gold", "gift"]
    assert [(r.id, r.status) for r in snapshot.claim_reviews] == [("gift", "rejected")]


def test_invalid_evidence_is_reported_and_blocks_even_when_accepted(
    client, tmp_path, rendered_case
):
    job_id = claims_job(tmp_path, rendered_case, broken_quote=True)
    review(client, job_id, {"origin": "accepted", "gold": "accepted"})
    detail = client.get(f"/api/jobs/{job_id}").json()
    origin = next(claim for claim in detail["claims"] if claim["id"] == "origin")
    assert origin["evidence"][0]["valid"] is False
    assert origin["evidence"][0]["reason"] == "quote_mismatch"
    assert origin["issues"] == ["missing_note_evidence", "invalid_evidence"]
    assert "invalid_evidence:origin" in detail["approval_issues"]
    assert approve(client, job_id, detail["content_digest"]).status_code == 409


def test_review_rejects_unknown_ids_bad_values_and_wrong_state(client, tmp_path, rendered_case):
    job_id = claims_job(tmp_path, rendered_case)
    seq = client.get(f"/api/jobs/{job_id}").json()["job"]["manifest_seq"]
    for decisions in ({"nope": "accepted"}, {"origin": "maybe"}, {}):
        response = review(client, job_id, decisions)
        assert response.status_code == 422, decisions
        assert response.json()["error"]["code"] == "E_INPUT_INVALID"
    assert review(client, job_id, {"origin": "accepted"}, actor="  ").status_code == 422
    assert client.get(f"/api/jobs/{job_id}").json()["job"]["manifest_seq"] == seq
    store = JobStore(tmp_path)
    head = store.load(job_id)
    store.commit(
        head,
        store.snapshot(head),
        state="FAILED",
        failed_stage="publish",
        pending_stage="publish",
        error={"code": "E_API_SCHEMA", "stage": "publish", "retryable": False, "detail": "x"},
    )
    with pytest.raises(AdLoomError) as error:
        review_claims(Settings(data_dir=tmp_path), job_id, {"origin": "accepted"}, "owner")
    assert error.value.error.code == "E_STATE_CONFLICT"
