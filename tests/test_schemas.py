import hashlib
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError

from adloom.schemas import (
    ApprovalRecord,
    ApprovalSubject,
    ArtifactRef,
    BBox,
    Brief,
    ClaimCandidate,
    CropPlan,
    EvidenceAssessment,
    Hook,
    JobManifest,
    MediaInfo,
    NoteDocument,
    NoteEvidence,
    Provenance,
    PublishOperation,
    PublishPlan,
    PublishResult,
    RemoteFileAttempt,
    RenderPlan,
    RenderSource,
    TimelinePlan,
    TrackCandidates,
    TrackResult,
    Understanding,
    approval_issues,
    assess_evidence,
)

SHA = "a" * 64
JOB = "b" * 32


def parse(model, value):
    return model.model_validate_json(json.dumps(value))


def media():
    return {
        "source_sha256": SHA,
        "normalized_sha256": "c" * 64,
        "source_width": 1920,
        "source_height": 1080,
        "duration_us": 10_000_000,
        "fps": {"numerator": 30, "denominator": 1},
        "frame_count": 300,
        "has_audio": False,
    }


def understanding():
    return {
        "source_duration_us": 10_000_000,
        "product_name": "컵",
        "sam_prompt": "ceramic cup",
        "key_moments": [{"start_us": 0, "end_us": 6_000_000, "reason": "제품"}],
        "hook_candidates": [
            {"id": "a", "text": "첫 문구"},
            {"id": "b", "text": "둘째 문구"},
            {"id": "c", "text": "셋째 문구"},
        ],
        "primary_text": "제품 설명",
        "headline": "제품",
        "cta": "LEARN_MORE",
    }


def timeline():
    return {
        "source_sha256": SHA,
        "source_duration_us": 10_000_000,
        "spans": [
            {
                "source_start_us": 0,
                "source_end_us": 6_000_000,
                "output_start_us": 0,
                "output_end_us": 6_000_000,
            }
        ],
    }


def subject():
    variants = []
    for aspect, height in (("9:16", 1920), ("4:5", 1350), ("1:1", 1080)):
        for hook in ("a", "b"):
            variants.append(
                {
                    "aspect": aspect,
                    "hook_id": hook,
                    "sha256": hashlib.sha256(f"{aspect}/{hook}".encode()).hexdigest(),
                    "frame_hash": SHA,
                    "duration_us": 8_000_000,
                    "width": 1080,
                    "height": height,
                    "origin_mode": "fixture",
                }
            )
    return {
        "job_id": JOB,
        "revision": 1,
        "execution_mode": "fixture",
        "source_sha256": SHA,
        "note_text": "컵 설명",
        "timeline": timeline(),
        "hooks": [{"id": "a", "text": "첫 문구"}, {"id": "b", "text": "둘째 문구"}],
        "primary_text": "제품 설명",
        "headline": "제품",
        "cta": "LEARN_MORE",
        "variants": variants,
        "thumbnails": [
            {"aspect": a, "sha256": SHA, "origin_mode": "fixture"} for a in ("9:16", "4:5", "1:1")
        ],
        "provider_provenance": [
            {
                "mode": "fixture",
                "stage": "understand",
                "kind": "provider",
                "model": "muse-spark-1.3",
                "capture_id": "fixture-spark",
            },
            {
                "mode": "fixture",
                "stage": "track",
                "kind": "provider",
                "model": "sam-3.1",
                "capture_id": "fixture-sam",
            },
            {
                "mode": "fixture",
                "stage": "enrich",
                "kind": "provider",
                "model": "muse-image-1.0",
                "capture_id": "fixture-image",
            },
        ],
        "policy_digest": SHA,
        "renderer_fingerprint": SHA,
        "publish_plan": {
            "execution_mode": "fixture",
            "account_id": "fixture-account",
            "page_id": "fixture-page",
            "graph_version": "fixture-v1",
            "daily_budget_krw": 10000,
            "cta": "LEARN_MORE",
            "profile": {
                "objective": "OUTCOME_TRAFFIC",
                "optimization_goal": "LINK_CLICKS",
                "billing_event": "IMPRESSIONS",
                "allowed_ctas": ["LEARN_MORE"],
            },
        },
    }


@pytest.mark.parametrize("duration", [2_999_999, 45_000_001, 60_000_000, True])
def test_media_rejects_out_of_range_duration(duration):
    value = media()
    value["duration_us"] = duration
    with pytest.raises(ValidationError):
        parse(MediaInfo, value)


def test_brief_normalizes_before_length_and_requires_a_note_source():
    value = {"video_path": "input/clip.mov", "region": "남양주", "daily_budget_krw": 1}
    with pytest.raises(ValidationError):
        parse(Brief, value)
    note = parse(Brief, {**value, "note_text": "\u1100\u1161" * 200})
    assert note.note_text == "가" * 200
    audio = parse(Brief, {**value, "note_audio_path": "input/note.wav"})
    assert audio.note_text is None
    with pytest.raises(ValidationError):
        parse(Brief, {**value, "note_text": " ", "note_audio_path": "input/note.wav"})


@pytest.mark.parametrize(
    "path", ["../clip.mp4", "/tmp/clip.mp4", "https://x.test/a.mp4", "a\\b.mp4"]
)
def test_brief_rejects_paths_outside_the_lexical_job_namespace(path):
    with pytest.raises(ValidationError):
        parse(
            Brief, {"video_path": path, "note_text": "설명", "region": "KR", "daily_budget_krw": 1}
        )


def test_understanding_enforces_intervals_and_hook_identity():
    valid = understanding()
    parse(Understanding, valid)
    for field, invalid in (
        ("key_moments", [{"start_us": 0, "end_us": 11_000_000, "reason": "초과"}]),
        (
            "key_moments",
            [
                {"start_us": 0, "end_us": 2, "reason": "a"},
                {"start_us": 1, "end_us": 3, "reason": "b"},
            ],
        ),
        ("hook_candidates", valid["hook_candidates"][:2]),
        ("hook_candidates", [valid["hook_candidates"][0]] * 3),
    ):
        with pytest.raises(ValidationError):
            parse(Understanding, {**valid, field: invalid})


def test_track_coverage_is_measured_before_interpolation():
    value = {
        "source_width": 100,
        "source_height": 100,
        "fps": {"numerator": 30, "denominator": 1},
        "frame_count": 2,
        "boxes": [{"x": 90, "y": 0, "w": 10, "h": 10, "score": None}, None],
        "coverage": 0.5,
    }
    result = parse(TrackResult, value)
    assert result.boxes[0].score is None
    with pytest.raises(ValidationError):
        parse(TrackResult, {**value, "coverage": 1})
    value["boxes"][0]["w"] = 11
    with pytest.raises(ValidationError):
        parse(TrackResult, value)


def test_unknown_object_selection_is_rejected():
    with pytest.raises(ValidationError):
        parse(TrackCandidates, {"tracks": [], "selected_object_id": "42"})


def test_crop_bounds_and_frame_count_are_checked():
    valid = {
        "aspect": "1:1",
        "source_width": 100,
        "source_height": 100,
        "frame_count": 2,
        "max_step_px": 5,
        "rects": [{"x": 0, "y": 0, "w": 100, "h": 100}] * 2,
    }
    parse(CropPlan, valid)
    with pytest.raises(ValidationError):
        parse(CropPlan, {**valid, "rects": valid["rects"][:1]})
    with pytest.raises(ValidationError):
        parse(CropPlan, {**valid, "rects": [{"x": 1, "y": 0, "w": 100, "h": 100}] * 2})


def test_timeline_uses_half_open_contiguous_output_and_counts_endcard():
    plan = parse(TimelinePlan, timeline())
    assert plan.duration_us == 8_000_000
    invalid = timeline()
    invalid["spans"][0]["output_start_us"] = 1
    with pytest.raises(ValidationError):
        parse(TimelinePlan, invalid)
    invalid = timeline()
    invalid["source_duration_us"] = 45_000_000
    invalid["spans"][0].update(source_end_us=30_000_000, output_end_us=30_000_000)
    with pytest.raises(ValidationError):
        parse(TimelinePlan, invalid)


def test_evidence_invalidity_is_per_reference_not_a_provider_schema_failure():
    note = NoteDocument(text="가\U0001d11e나")
    reference = NoteEvidence(source_digest=note.sha256, start=1, end=2, quote="\U0001d11e")
    valid = assess_evidence("ref", reference, note=note)
    assert valid.valid
    invalid = assess_evidence(
        "ref",
        NoteEvidence(source_digest=note.sha256, start=1, end=3, quote="\U0001d11e"),
        note=note,
    )
    assert not invalid.valid and invalid.reason == "quote_mismatch"
    with pytest.raises(ValidationError):
        EvidenceAssessment(id="ref", reference=reference, valid=False)


def test_provider_cannot_supply_a_review_decision():
    with pytest.raises(ValidationError):
        ClaimCandidate(id="c", text="설명", classification="inference", status="accepted")
    with pytest.raises(ValidationError):
        Provenance(
            mode="live",
            stage="understand",
            kind="provider",
            model="muse-spark-1.3-contributor",
            capture_id="x",
        )


def test_render_source_cannot_be_a_generated_or_remote_video():
    with pytest.raises(ValidationError):
        RenderSource(source_type="generated_video", media_type="video", path="a.mp4", sha256=SHA)
    with pytest.raises(ValidationError):
        RenderSource(
            source_type="input_video", media_type="video", path="https://x.test/a.mp4", sha256=SHA
        )


def test_approval_round_trip_and_digest_change_with_real_content():
    value = subject()
    approved = parse(ApprovalSubject, value)
    assert not approval_issues(approved)
    assert (
        ApprovalSubject.model_validate_json(approved.model_dump_json()).content_digest()
        == approved.content_digest()
    )
    changed = deepcopy(value)
    changed["publish_plan"]["daily_budget_krw"] += 1
    assert parse(ApprovalSubject, changed).content_digest() != approved.content_digest()
    record = parse(
        ApprovalRecord,
        {
            "job_id": JOB,
            "revision": 1,
            "content_digest": approved.content_digest(),
            "approved_at": "2026-10-25T12:00:00Z",
            "actor": "operator",
            "channel": "cli",
        },
    )
    assert record.matches(approved)
    assert not record.matches(parse(ApprovalSubject, changed))


def test_six_distinct_variants_and_mode_consistency_are_mandatory():
    value = subject()
    with pytest.raises(ValidationError):
        parse(ApprovalSubject, {**value, "variants": value["variants"][:5]})
    duplicate = deepcopy(value)
    duplicate["variants"][-1] = duplicate["variants"][0]
    with pytest.raises(ValidationError):
        parse(ApprovalSubject, duplicate)
    contaminated = deepcopy(value)
    contaminated["variants"][0]["origin_mode"] = "live"
    with pytest.raises(ValidationError):
        parse(ApprovalSubject, contaminated)


def test_pending_claim_and_block_policy_prevent_approval():
    value = subject()
    value["claims"] = [
        {"id": "c", "text": "효능", "classification": "inference", "high_risk": True}
    ]
    value["policy_flags"] = [
        {
            "field": "headline",
            "original": "효능",
            "rule_id": "r",
            "severity": "block",
            "rewrite": "제품",
        }
    ]
    issues = approval_issues(parse(ApprovalSubject, value))
    assert "policy_block" in issues
    assert "unsupported_high_risk_claim:c" in issues
    assert "unreviewed_claim:c" in issues


def test_rejected_claim_blocks_approval_even_when_optional():
    value = subject()
    value["claims"] = [
        {
            "id": "gift",
            "text": "선물",
            "classification": "inference",
            "status": "rejected",
            "actor": "owner",
        }
    ]
    assert approval_issues(parse(ApprovalSubject, value)) == ("rejected_claim:gift",)


def test_post_journal_cannot_confirm_without_an_id_or_mix_modes():
    prepared = {
        "job_id": JOB,
        "revision": 1,
        "execution_mode": "fixture",
        "resource_kind": "campaign",
        "request_fingerprint": SHA,
        "phase": "PREPARED",
    }
    with pytest.raises(ValidationError):
        parse(PublishOperation, {**prepared, "phase": "CONFIRMED"})
    with pytest.raises(ValidationError):
        parse(PublishOperation, {**prepared, "remote_id": "orphan"})


def test_job_head_requires_a_run_owner_and_valid_approval_reference():
    created = {
        "job_id": JOB,
        "revision": 1,
        "manifest_seq": 1,
        "execution_mode": "fixture",
        "state": "CREATED",
        "last_success_state": "CREATED",
        "run_state": "IDLE",
        "note_status": "CONFIRMED",
        "manifest_ref": {"path": "revisions/r1/m1.json", "sha256": SHA},
        "created_at": "2026-10-25T12:00:00Z",
        "updated_at": "2026-10-25T12:00:00Z",
    }
    parse(JobManifest, created)
    with pytest.raises(ValidationError):
        parse(JobManifest, {**created, "run_state": "RUNNING"})
    with pytest.raises(ValidationError):
        parse(JobManifest, {**created, "state": "APPROVED", "last_success_state": "APPROVED"})
    with pytest.raises(ValidationError):
        parse(JobManifest, {**created, "created_at": "2026-10-25T12:00:00"})


@pytest.mark.parametrize("number", [float("nan"), float("inf"), True, "1"])
def test_geometry_rejects_nonfinite_and_coerced_numbers(number):
    with pytest.raises(ValidationError):
        parse(BBox, {"x": number, "y": 0, "w": 1, "h": 1})


def test_approval_does_not_trust_a_forged_valid_evidence_flag():
    value = subject()
    note = NoteDocument(text=value["note_text"])
    value["evidence"] = [
        {
            "id": "forged",
            "valid": True,
            "reference": {
                "kind": "note",
                "source_digest": note.sha256,
                "start": 0,
                "end": 1,
                "quote": "다른 값",
            },
        }
    ]
    value["claims"] = [
        {
            "id": "price",
            "text": "가격",
            "classification": "explicit",
            "high_risk": True,
            "reference_ids": ["forged"],
            "status": "accepted",
            "actor": "operator",
        }
    ]
    issues = approval_issues(parse(ApprovalSubject, value))
    assert "invalid_evidence:price" in issues
    assert "unsupported_high_risk_claim:price" in issues


def test_semantically_identical_variant_order_has_the_same_approval_digest():
    value = subject()
    other = deepcopy(value)
    other["variants"].reverse()
    assert (
        parse(ApprovalSubject, value).content_digest()
        == parse(ApprovalSubject, other).content_digest()
    )


def test_publish_plan_cannot_hide_assets_or_unpaused_status():
    value = subject()["publish_plan"]
    with pytest.raises(ValidationError):
        parse(PublishPlan, {**value, "asset_sha256": SHA})
    with pytest.raises(ValidationError):
        parse(PublishPlan, {**value, "ad_status": "ACTIVE"})
    with pytest.raises(ValidationError):
        parse(PublishPlan, {**value, "cta": "SHOP_NOW"})
    with pytest.raises(ValidationError):
        parse(PublishPlan, {**value, "daily_budget_krw": True})


def test_live_publish_requires_explicit_live_identifiers_and_destination():
    value = subject()["publish_plan"]
    value.update(execution_mode="live", account_id="123", page_id="456", graph_version="v26.0")
    with pytest.raises(ValidationError):
        parse(PublishPlan, value)
    value["destination_url"] = "https://example.test/product"
    assert parse(PublishPlan, value).destination_url.host == "example.test"
    with pytest.raises(ValidationError):
        parse(PublishPlan, {**value, "page_id": "fixture-page"})


def test_unknown_upload_retry_requires_human_acknowledgement():
    value = {
        "attempt_id": JOB,
        "source_sha256": SHA,
        "phase": "UNKNOWN",
        "error": {
            "code": "E_API_NETWORK",
            "stage": "understand",
            "retryable": False,
            "detail": "response lost",
        },
    }
    parse(RemoteFileAttempt, value)
    with pytest.raises(ValidationError):
        parse(RemoteFileAttempt, {**value, "new_attempt_authorized": True})
    assert parse(
        RemoteFileAttempt, {**value, "new_attempt_authorized": True, "abandoned_by": "operator"}
    ).new_attempt_authorized


def test_publish_result_requires_two_distinct_ads_and_preserves_effective_status():
    first = {
        "hook_id": "a",
        "video_id": "video-a",
        "creative_id": "creative-a",
        "ad_id": "ad-a",
        "configured_status": "PAUSED",
        "effective_status": "CAMPAIGN_PAUSED",
    }
    second = {
        **first,
        "hook_id": "b",
        "video_id": "video-b",
        "creative_id": "creative-b",
        "ad_id": "ad-b",
    }
    value = {
        "job_id": JOB,
        "revision": 1,
        "execution_mode": "fixture",
        "campaign_id": "campaign",
        "adset_id": "adset",
        "campaign_status": "PAUSED",
        "adset_status": "PAUSED",
        "ads": [first, second],
        "thumbnail_hashes": ["thumbnail"],
        "checked_at": "2026-10-25T12:00:00Z",
    }
    assert parse(PublishResult, value).ads[0].effective_status == "CAMPAIGN_PAUSED"
    with pytest.raises(ValidationError):
        parse(PublishResult, {**value, "ads": [first, first]})


def test_decoded_json_arrays_become_immutable_without_relaxing_scalars():
    value = understanding()
    result = Understanding.model_validate(value)
    assert isinstance(result.hook_candidates, tuple)
    assert result == Understanding.model_validate_json(json.dumps(value))
    value["source_duration_us"] = "10000000"
    with pytest.raises(ValidationError):
        Understanding.model_validate(value)


def test_decoded_approval_payload_matches_raw_json_validation():
    value = subject()
    assert (
        ApprovalSubject.model_validate(value).content_digest()
        == parse(ApprovalSubject, value).content_digest()
    )


def test_decoded_timestamps_are_aware_and_normalized_without_epoch_coercion():
    value = {
        "job_id": JOB,
        "revision": 1,
        "content_digest": SHA,
        "approved_at": "2026-10-25T21:00:00+09:00",
        "actor": "operator",
        "channel": "web",
    }
    record = ApprovalRecord.model_validate(value)
    assert record.approved_at.isoformat() == "2026-10-25T12:00:00+00:00"
    for invalid in ("2026-10-25T12:00:00", 1792929600, True):
        with pytest.raises(ValidationError):
            ApprovalRecord.model_validate({**value, "approved_at": invalid})


def test_media_duration_cannot_reference_a_nonexistent_frame():
    with pytest.raises(ValidationError):
        parse(MediaInfo, {**media(), "duration_us": 10_033_333})


def span(start, end, offset, repeat=0):
    return {
        "source_start_us": start * 1_000_000,
        "source_end_us": end * 1_000_000,
        "output_start_us": offset * 1_000_000,
        "output_end_us": (offset + end - start) * 1_000_000,
        "repeat_index": repeat,
    }


@pytest.mark.parametrize(
    "spans",
    [
        [span(0, 6, 0), span(0, 6, 6)],
        [span(5, 10, 0), span(0, 5, 5)],
        [span(0, 6, 0, repeat=3)],
        [span(0, 6, 0), span(0, 1, 6, repeat=1)],
    ],
)
def test_timeline_rejects_reordering_unmarked_or_unnecessary_repeats(spans):
    with pytest.raises(ValidationError):
        parse(TimelinePlan, {**timeline(), "spans": spans})


def test_short_source_can_be_padded_with_an_explicit_repeat():
    plan = parse(
        TimelinePlan,
        {
            **timeline(),
            "source_duration_us": 3_000_000,
            "spans": [span(0, 3, 0), span(0, 3, 3, repeat=1)],
        },
    )
    assert plan.duration_us == 8_000_000
    assert plan.spans[1].repeat_index == 1


def render_plan():
    source = media()
    image_digest = "d" * 64
    images = [
        {
            "aspect": aspect,
            "path": f"images/{i}.png",
            "sha256": image_digest,
            "origin_mode": "fixture",
        }
        for i, aspect in enumerate(("9:16", "4:5", "1:1"))
    ]
    return {
        "revision": 1,
        "media": source,
        "font_sha256": SHA,
        "renderer_fingerprint": SHA,
        "sources": [
            {
                "source_type": "input_video",
                "media_type": "video",
                "path": "input/clip.mp4",
                "sha256": source["normalized_sha256"],
            },
            {
                "source_type": "muse_image",
                "media_type": "image",
                "path": "images/card.png",
                "sha256": image_digest,
            },
        ],
        "timeline": {**timeline(), "source_sha256": source["normalized_sha256"]},
        "crop_plans": [
            {
                "aspect": aspect,
                "source_width": 1920,
                "source_height": 1080,
                "frame_count": 300,
                "max_step_px": 5,
                "rects": [{"x": 0, "y": 0, "w": width, "h": 1080}] * 300,
            }
            for aspect, width in (("9:16", 607.5), ("4:5", 864), ("1:1", 1080))
        ],
        "hooks": [{"id": "a", "text": "첫 문구"}, {"id": "b", "text": "둘째 문구"}],
        "enrichment": {"source_duration_us": 10_000_000, "thumbnails": images, "endcards": images},
    }


def test_render_plan_has_one_video_and_only_declared_endcard_sources():
    value = render_plan()
    parse(RenderPlan, value)
    with pytest.raises(ValidationError):
        parse(
            RenderPlan,
            {
                **value,
                "sources": value["sources"]
                + [
                    {
                        "source_type": "input_video",
                        "media_type": "video",
                        "path": "input/other.mp4",
                        "sha256": "e" * 64,
                    },
                ],
            },
        )
    with pytest.raises(ValidationError):
        parse(RenderPlan, {**value, "sources": value["sources"][:1]})


@pytest.mark.parametrize("hook_id", ["hook/1", "\u0000", "x" * 300, "_shared"])
def test_hook_ids_are_safe_for_journal_keys(hook_id):
    with pytest.raises(ValidationError):
        Hook(id=hook_id, text="문구")
    with pytest.raises(ValidationError):
        PublishOperation(
            job_id=JOB,
            revision=1,
            execution_mode="fixture",
            resource_kind="image",
            hook_id=hook_id,
            request_fingerprint=SHA,
            phase="PREPARED",
        )


def test_shared_and_named_image_operations_have_different_keys():
    value = {
        "job_id": JOB,
        "revision": 1,
        "execution_mode": "fixture",
        "resource_kind": "image",
        "request_fingerprint": SHA,
        "phase": "PREPARED",
    }
    assert (
        parse(PublishOperation, value).operation_key
        != parse(PublishOperation, {**value, "hook_id": "shared"}).operation_key
    )
    with pytest.raises(ValidationError):
        parse(PublishOperation, {**value, "revision": 2**53})


def test_failed_head_must_be_valid_at_its_resume_state():
    value = {
        "job_id": JOB,
        "revision": 1,
        "manifest_seq": 1,
        "execution_mode": "fixture",
        "state": "FAILED",
        "last_success_state": "AWAITING_APPROVAL",
        "run_state": "IDLE",
        "note_status": "AUDIO_PENDING",
        "manifest_ref": {"path": "r1/m1.json", "sha256": SHA},
        "failed_stage": "assemble",
        "pending_stage": "assemble",
        "error": {
            "code": "E_RENDER_FAILED",
            "stage": "assemble",
            "retryable": True,
            "detail": "diagnostic",
        },
        "created_at": "2026-10-25T12:00:00Z",
        "updated_at": "2026-10-25T12:00:00Z",
    }
    with pytest.raises(ValidationError):
        parse(JobManifest, value)
    assert parse(JobManifest, {**value, "note_status": "CONFIRMED"}).state == "FAILED"


def test_prepared_operation_can_be_explicitly_abandoned():
    operation = PublishOperation(
        job_id=JOB,
        revision=1,
        execution_mode="fixture",
        resource_kind="campaign",
        request_fingerprint=SHA,
        phase="PREPARED",
        abandoned=True,
        resolution_actor="operator",
    )
    assert operation.abandoned and operation.remote_id is None


def test_image_fallback_cannot_be_claimed_by_a_voice_failure():
    value = subject()
    value["image_fallback"] = True
    value["warnings"] = ["Image unavailable"]
    fallback = {
        "mode": "fixture",
        "stage": "enrich",
        "kind": "local_fallback",
        "model": "muse-voice-transcribe-1.0",
        "reason": "provider failure",
    }
    value["provider_provenance"][-1] = fallback
    with pytest.raises(ValidationError):
        parse(ApprovalSubject, value)
    value["provider_provenance"][-1] = {**fallback, "model": "muse-image-1.0"}
    assert not approval_issues(parse(ApprovalSubject, value))


def test_operation_identity_is_mode_separated_and_fits_a_journal_path():
    value = {
        "job_id": JOB,
        "revision": 1,
        "execution_mode": "fixture",
        "resource_kind": "campaign",
        "request_fingerprint": SHA,
        "phase": "PREPARED",
    }
    fixture = PublishOperation.model_validate(value)
    live = PublishOperation.model_validate({**value, "execution_mode": "live"})
    assert fixture.operation_key != live.operation_key
    reference = ArtifactRef(path=f"publish/{fixture.operation_key}.json", sha256=SHA)
    assert reference.path.count("/") == 1
