"""Approval-bound, journaled publishing. Every resource is created PAUSED."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import ValidationError

from adloom.adapters.base import MarketingPublisher, PublishNotSent
from adloom.config import AdLoomError, Settings
from adloom.jobs import JobStore, Snapshot, atomic_write, file_hash
from adloom.policy import POLICY_DIGEST, check, understanding_fields
from adloom.schemas import (
    ApprovalRecord,
    ApprovalSubject,
    ArtifactRef,
    ClaimReview,
    EvidenceAssessment,
    ImageDigest,
    JobManifest,
    MarketingProfile,
    NoteDocument,
    PublishedAd,
    PublishOperation,
    PublishPlan,
    PublishResult,
    approval_issues,
    assess_evidence,
)

Resource = Literal["video", "image", "creative", "campaign", "adset", "ad"]


PROFILE = MarketingProfile(
    objective="OUTCOME_TRAFFIC",
    optimization_goal="LINK_CLICKS",
    billing_event="IMPRESSIONS",
    allowed_ctas=("LEARN_MORE",),
)


def fixture_publish_plan(snapshot: Snapshot) -> PublishPlan:
    if snapshot.understanding is None:
        raise AdLoomError("E_STATE_CONFLICT", "publish", "Understanding is required")
    return PublishPlan(
        execution_mode="fixture",
        account_id="fixture-account",
        page_id="fixture-page",
        graph_version="fixture-v1",
        daily_budget_krw=snapshot.brief.daily_budget_krw,
        destination_url=snapshot.brief.destination_url,
        cta=snapshot.understanding.cta,
        profile=PROFILE,
    )


def live_publish_plan(snapshot: Snapshot, settings: Settings) -> PublishPlan:
    """Plan for the configured Meta account; the approval digest covers every value."""
    if snapshot.understanding is None:
        raise AdLoomError("E_STATE_CONFLICT", "publish", "Understanding is required")
    account, page, version = (
        settings.meta_ad_account_id,
        settings.meta_page_id,
        settings.meta_graph_version,
    )
    if settings.mode != "live" or account is None or page is None or version is None:
        raise AdLoomError("E_API_AUTH", "publish", "Live publishing settings are incomplete")
    if snapshot.brief.destination_url is None:
        raise AdLoomError(
            "E_INPUT_INVALID", "publish", "Live publishing requires a destination URL"
        )
    try:
        return PublishPlan(
            execution_mode="live",
            account_id=account.removeprefix("act_"),
            page_id=page,
            graph_version=version,
            daily_budget_krw=snapshot.brief.daily_budget_krw,
            destination_url=snapshot.brief.destination_url,
            cta=snapshot.understanding.cta,
            profile=PROFILE,
        )
    except ValidationError:
        raise AdLoomError("E_API_AUTH", "publish", "Live publishing settings are invalid") from None


def publish_plan(snapshot: Snapshot, settings: Settings) -> PublishPlan:
    if settings.mode == "live":
        return live_publish_plan(snapshot, settings)
    return fixture_publish_plan(snapshot)


def claim_reviews(
    snapshot: Snapshot,
) -> tuple[tuple[EvidenceAssessment, ...], tuple[ClaimReview, ...]]:
    """Assess every claim reference against the confirmed note and the normalized source.

    Evidence IDs are ``<claim id>#<n>`` (1-based reference index). A claim is pending until
    the owner decides; a stored decision only applies while its claim text is unchanged.
    No schema rule marks a claim high-risk yet, so high_risk stays False.
    """
    understanding = snapshot.understanding
    if understanding is None:
        return (), ()
    note = NoteDocument(text=snapshot.brief.note_text) if snapshot.brief.note_text else None
    decided = {review.id: review for review in snapshot.claim_reviews}
    evidence: list[EvidenceAssessment] = []
    claims: list[ClaimReview] = []
    for claim in understanding.claims:
        ids = tuple(f"{claim.id}#{index}" for index in range(1, len(claim.references) + 1))
        evidence += [
            assess_evidence(key, reference, note=note, media=snapshot.media)
            for key, reference in zip(ids, claim.references, strict=True)
        ]
        decision = decided.get(claim.id)
        if decision is not None and decision.text != claim.text:
            decision = None
        claims.append(
            ClaimReview(
                id=claim.id,
                text=claim.text,
                classification=claim.classification,
                reference_ids=ids,
                status=decision.status if decision is not None else "pending",
                actor=decision.actor if decision is not None else None,
            )
        )
    return tuple(evidence), tuple(claims)


def make_subject(store: JobStore, head: JobManifest, snapshot: Snapshot) -> ApprovalSubject:
    understanding, enrichment, plan = (
        snapshot.understanding,
        snapshot.enrichment,
        snapshot.render_plan,
    )
    if understanding is None or enrichment is None or plan is None or snapshot.publish_plan is None:
        raise AdLoomError("E_APPROVAL_REQUIRED", "publish", "Render and publish plans are required")
    # Claims never block here; approval_issues judges their review state and evidence.
    evidence, claims = claim_reviews(snapshot)
    artifacts: list[ArtifactRef] = [
        ArtifactRef(path=snapshot.brief.video_path, sha256=snapshot.media.normalized_sha256)
    ]
    artifacts += [ArtifactRef(path=v.path, sha256=v.sha256) for v in snapshot.variants]
    artifacts += [
        ArtifactRef(path=i.path, sha256=i.sha256)
        for i in (*enrichment.thumbnails, *enrichment.endcards)
    ]
    for artifact in artifacts:
        path = store.path(head.job_id, artifact.path)
        if not path.is_file() or file_hash(path) != artifact.sha256:
            raise AdLoomError(
                "E_APPROVAL_REQUIRED", "publish", "Reviewed asset is missing or changed"
            )
    fields = understanding_fields(understanding)
    fields.update(
        {f"subtitle:{i}": segment.text for i, segment in enumerate(enrichment.transcript)}
    )
    images = tuple(
        ImageDigest(aspect=i.aspect, sha256=i.sha256, origin_mode=i.origin_mode)
        for i in enrichment.thumbnails
    )
    return ApprovalSubject(
        job_id=head.job_id,
        revision=head.revision,
        execution_mode=head.execution_mode,
        source_sha256=snapshot.media.normalized_sha256,
        note_text=snapshot.brief.note_text or "",
        timeline=plan.timeline,
        hooks=plan.hooks,
        primary_text=understanding.primary_text,
        headline=understanding.headline,
        cta=understanding.cta,
        variants=tuple(v.approval_projection() for v in snapshot.variants),
        thumbnails=(images[0], images[1], images[2]),
        provider_provenance=snapshot.provenance,
        evidence=evidence,
        claims=claims,
        policy_flags=check(fields),
        warnings=enrichment.warnings,
        degraded=any(c.degraded for c in snapshot.crops),
        clipped=any(c.clipped_frames or c.safe_area_violation_frames for c in snapshot.crops),
        image_fallback=enrichment.image_fallback,
        policy_digest=POLICY_DIGEST,
        renderer_fingerprint=plan.renderer_fingerprint,
        publish_plan=snapshot.publish_plan,
    )


def approve(
    store: JobStore,
    head: JobManifest,
    actor: str,
    channel: Literal["cli", "web"] = "cli",
    expected_digest: str | None = None,
) -> JobManifest:
    if head.state != "AWAITING_APPROVAL":
        raise AdLoomError("E_APPROVAL_REQUIRED", "publish", "Job is not awaiting approval")
    snapshot = store.snapshot(head)
    subject = make_subject(store, head, snapshot)
    if expected_digest is not None and expected_digest != subject.content_digest():
        raise AdLoomError("E_REVISION_CONFLICT", "publish", "Review changed; inspect it again")
    if approval_issues(subject):
        raise AdLoomError(
            "E_POLICY_BLOCK", "publish", "Resolve policy or evidence issues before approval"
        )
    record = ApprovalRecord(
        job_id=head.job_id,
        revision=head.revision,
        content_digest=subject.content_digest(),
        approved_at=datetime.now(UTC),
        actor=actor,
        channel=channel,
    )
    relative = f"revisions/r{head.revision:06d}/approval.json"
    path = store.path(head.job_id, relative)
    atomic_write(path, record.model_dump_json().encode())
    return store.transition(
        head,
        "APPROVED",
        snapshot.model_copy(update={"approval_subject": subject}),
        approval_ref=ArtifactRef(path=relative, sha256=file_hash(path)),
    )


def operations(store: JobStore, job_id: str) -> list[PublishOperation]:
    return sorted(
        (
            PublishOperation.model_validate_json(path.read_bytes())
            for path in store.path(job_id, "publish").glob("*.json")
        ),
        key=lambda operation: operation.operation_key,
    )


def unresolved(operation: PublishOperation) -> bool:
    return operation.phase in {"PREPARED", "UNKNOWN"} and not operation.abandoned


def abandon(store: JobStore, head: JobManifest, operation_key: str, actor: str) -> JobManifest:
    """Record the owner's decision to stop retrying an operation whose outcome is unknown.

    The request is never resent; the job stays FAILED at publish and cannot publish again.
    """
    if not operation_key.startswith(f"{head.job_id}.") or not re.fullmatch(
        r"[A-Za-z0-9_.-]+", operation_key
    ):
        raise AdLoomError("E_INPUT_INVALID", "publish", "Unknown publish operation")
    path = store.path(head.job_id, f"publish/{operation_key}.json")
    if not path.is_file():
        raise AdLoomError("E_INPUT_INVALID", "publish", "Unknown publish operation")
    operation = PublishOperation.model_validate_json(path.read_bytes())
    if operation.operation_key != operation_key or not unresolved(operation):
        raise AdLoomError(
            "E_STATE_CONFLICT", "publish", "Only an unresolved publish request can be abandoned"
        )
    marked = PublishOperation.model_validate(
        {**operation.model_dump(), "abandoned": True, "resolution_actor": actor}
    )
    atomic_write(path, marked.model_dump_json().encode())
    error = AdLoomError(
        "E_STATE_CONFLICT", "publish", "Publishing was abandoned; start a new job"
    ).error
    return store.commit(
        head,
        store.snapshot(head),
        state="FAILED",
        failed_stage="publish",
        pending_stage="publish",
        error=error,
        run_state="IDLE",
        active_run_id=None,
    )


def _operation(
    store: JobStore,
    head: JobManifest,
    adapter: MarketingPublisher,
    kind: Resource,
    payload: dict[str, object],
    hook_id: str | None = None,
) -> str:
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    operation = PublishOperation(
        job_id=head.job_id,
        revision=head.revision,
        execution_mode=head.execution_mode,
        resource_kind=kind,
        hook_id=hook_id,
        request_fingerprint=fingerprint,
        phase="PREPARED",
    )
    path = store.path(head.job_id, f"publish/{operation.operation_key}.json")
    if path.exists():
        previous = PublishOperation.model_validate_json(path.read_bytes())
        if previous.request_fingerprint != fingerprint:
            raise AdLoomError("E_APPROVAL_REQUIRED", "publish", "Publish request changed")
        if previous.phase == "CONFIRMED" and previous.remote_id is not None:
            return previous.remote_id
        if previous.phase in {"PREPARED", "UNKNOWN"}:
            raise AdLoomError(
                "E_PUBLISH_PARTIAL", "publish", "Previous request outcome is unknown; do not resend"
            )
    atomic_write(path, operation.model_dump_json().encode())
    try:
        remote_id = adapter.create(kind, payload, operation.operation_key)
    except AdLoomError as error:
        failed = operation.model_copy(
            update={
                "phase": "FAILED" if isinstance(error, PublishNotSent) else "UNKNOWN",
                "error": error.error,
            }
        )
        atomic_write(path, failed.model_dump_json().encode())
        raise
    except Exception:
        unknown_error = AdLoomError(
            "E_PUBLISH_PARTIAL", "publish", "Request outcome unknown; do not resend"
        )
        atomic_write(
            path,
            operation.model_copy(update={"phase": "UNKNOWN", "error": unknown_error.error})
            .model_dump_json()
            .encode(),
        )
        raise unknown_error from None
    confirmed = PublishOperation.model_validate(
        {**operation.model_dump(), "phase": "CONFIRMED", "remote_id": remote_id}
    )
    atomic_write(path, confirmed.model_dump_json().encode())
    return remote_id


def publish(store: JobStore, head: JobManifest, adapter: MarketingPublisher) -> JobManifest:
    if any(operation.abandoned for operation in operations(store, head.job_id)):
        raise AdLoomError(
            "E_STATE_CONFLICT", "publish", "Publishing was abandoned; start a new job"
        )
    if head.state == "FAILED" and head.failed_stage == "publish":
        head = store.resume(head)
    if head.state not in {"APPROVED", "PUBLISHED_PAUSED"} or head.approval_ref is None:
        raise AdLoomError("E_APPROVAL_REQUIRED", "publish", "Human approval is required")
    snapshot = store.snapshot(head)
    path = store.path(head.job_id, head.approval_ref.path)
    if not path.is_file() or file_hash(path) != head.approval_ref.sha256:
        raise AdLoomError("E_APPROVAL_REQUIRED", "publish", "Approval record is missing or changed")
    subject = make_subject(store, head, snapshot)
    record = ApprovalRecord.model_validate_json(path.read_bytes())
    if not record.matches(subject):
        raise AdLoomError(
            "E_APPROVAL_REQUIRED", "publish", "Approval no longer matches current content"
        )
    if head.state == "PUBLISHED_PAUSED":
        return head
    plan = subject.publish_plan
    if plan.execution_mode != head.execution_mode:
        raise AdLoomError("E_STATE_CONFLICT", "publish", "Publish plan mode differs from the job")
    enrichment = snapshot.enrichment
    assert enrichment is not None  # make_subject requires it
    head = store.start_run(head, "publish")
    try:
        campaign = _operation(
            store,
            head,
            adapter,
            "campaign",
            {
                "name": head.job_id,
                "objective": plan.profile.objective,
                "status": "PAUSED",
                "special_ad_categories": [],
            },
        )
        adset = _operation(
            store,
            head,
            adapter,
            "adset",
            {
                "campaign_id": campaign,
                "daily_budget": plan.daily_budget_krw,
                "status": "PAUSED",
                "optimization_goal": plan.profile.optimization_goal,
                "billing_event": plan.profile.billing_event,
                "targeting": {"geo_locations": {"countries": ["KR"]}},
            },
        )
        thumbnail = next(i for i in enrichment.thumbnails if i.aspect == "9:16")
        image = _operation(
            store, head, adapter, "image", {"sha256": thumbnail.sha256, "path": thumbnail.path}
        )
        ads = []
        for variant in sorted(snapshot.variants, key=lambda v: (v.aspect, v.hook_id)):
            if variant.aspect != "9:16":
                continue
            video = _operation(
                store,
                head,
                adapter,
                "video",
                {"sha256": variant.sha256, "path": variant.path},
                variant.hook_id,
            )
            creative = _operation(
                store,
                head,
                adapter,
                "creative",
                {
                    "page_id": plan.page_id,
                    "video_id": video,
                    "image_hash": image,
                    "primary_text": subject.primary_text,
                    "headline": subject.headline,
                    "cta": subject.cta,
                    "destination_url": str(plan.destination_url) if plan.destination_url else None,
                },
                variant.hook_id,
            )
            ad = _operation(
                store,
                head,
                adapter,
                "ad",
                {"adset_id": adset, "creative_id": creative, "status": "PAUSED"},
                variant.hook_id,
            )
            ads.append(
                PublishedAd(
                    hook_id=variant.hook_id,
                    video_id=video,
                    creative_id=creative,
                    ad_id=ad,
                    configured_status="PAUSED",
                    effective_status="PAUSED",
                )
            )
        result = PublishResult(
            job_id=head.job_id,
            revision=head.revision,
            execution_mode=plan.execution_mode,
            campaign_id=campaign,
            adset_id=adset,
            campaign_status="PAUSED",
            adset_status="PAUSED",
            ads=(ads[0], ads[1]),
            thumbnail_hashes=(image,),
            checked_at=datetime.now(UTC),
        )
        atomic_write(store.path(head.job_id, "publish.json"), result.model_dump_json().encode())
        return store.transition(
            head, "PUBLISHED_PAUSED", snapshot.model_copy(update={"publish_result": result})
        )
    except AdLoomError as error:
        store.fail(head, "publish", error.error)
        raise
