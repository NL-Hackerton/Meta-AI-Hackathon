"""Shared synchronous commands for the local, explicitly offline AdLoom workflow."""

import json
import shutil
import subprocess
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from adloom.adapters.base import get_adapters
from adloom.config import AdLoomError, Settings, require_live_ready
from adloom.jobs import NEXT_STAGE, JobStore, atomic_write
from adloom.policy import check, understanding_fields
from adloom.schemas import (
    Brief,
    ClaimReview,
    JobManifest,
    JobState,
    Provenance,
    Stage,
    Understanding,
    approval_issues,
)
from adloom.stages.assemble import assemble
from adloom.stages.enrich import enrich
from adloom.stages.input import fill_note, normalize
from adloom.stages.publish import (
    abandon,
    approve,
    claim_reviews,
    make_subject,
    operations,
    publish,
    publish_plan,
    unresolved,
)
from adloom.stages.track import track
from adloom.stages.understand import understand

NOTE_AUDIO_SUFFIXES = frozenset({".webm", ".ogg", ".m4a", ".mp4", ".wav", ".mp3"})


def _check_mode(settings: Settings, head: JobManifest) -> None:
    """Fixture and live artifacts never mix: a job only runs in the mode it was created in."""
    if head.execution_mode != settings.mode:
        raise AdLoomError(
            "E_STATE_CONFLICT",
            head.pending_stage or "input",
            f"This is a {head.execution_mode} job; it cannot run in {settings.mode} mode",
        )
    require_live_ready(settings, head.pending_stage or "input")


def _record_cleanup(store: JobStore, job_id: str, warnings: list[str]) -> None:
    """Persist Model Files cleanup failures so the owner can delete leftovers by hand."""
    if not warnings:
        return
    path = store.path(job_id, "cleanup_warnings.json")
    previous: list[str] = json.loads(path.read_bytes()) if path.is_file() else []
    atomic_write(path, json.dumps([*previous, *warnings], ensure_ascii=False).encode())


def _run(settings: Settings, store: JobStore, head: JobManifest) -> JobManifest:
    _check_mode(settings, head)
    root = store.path(head.job_id)
    adapters = get_adapters(settings, root)
    mode = settings.mode
    cleanup: list[str] = []
    if head.state == "FAILED":
        if head.failed_stage == "publish":
            return publish(store, head, adapters.marketing)
        head = store.resume(head)
    # A RUNNING head left by a crashed process continues from its last successful state.
    first: Stage | None = NEXT_STAGE.get(head.state)
    if head.state == "CREATED" and head.note_status != "CONFIRMED":
        first = "input" if head.note_status == "AUDIO_PENDING" else None
    if first is None:
        return store.end_run(head)
    head = store.start_run(head, first)
    stage: Stage = "input"
    try:
        snapshot = store.snapshot(head)
        if head.state == "CREATED":
            if head.note_status == "AUDIO_PENDING":
                # A transcript is only a proposal; the owner confirms it before understanding.
                proposal = fill_note(snapshot.brief, root, adapters.voice).note_text
                return store.commit(
                    head,
                    snapshot.model_copy(update={"note_proposal": proposal}),
                    note_status="REVIEW_REQUIRED",
                    run_state="IDLE",
                    active_run_id=None,
                    pending_stage=None,
                )
            brief = snapshot.brief
            stage = "understand"
            try:
                result = understand(
                    root / "input/source.mp4",
                    brief.note_text or "",
                    brief.language,
                    adapters.spark,
                    cleanup,
                )
            finally:
                _record_cleanup(store, head.job_id, cleanup)
                cleanup.clear()
            if result.source_duration_us != snapshot.media.duration_us:
                raise AdLoomError(
                    "E_API_SCHEMA", stage, "Understanding duration differs from normalized video"
                )
            origin = Provenance(
                mode=mode,
                stage=stage,
                kind="provider",
                model=settings.spark_model,
                capture_id=snapshot.media.source_sha256,
            )
            snapshot = snapshot.model_copy(
                update={
                    "brief": brief,
                    "understanding": result,
                    "provenance": (*snapshot.provenance, origin),
                }
            )
            snapshot = snapshot.model_copy(
                update={"publish_plan": publish_plan(snapshot, settings)}
            )
            atomic_write(root / "understanding.json", result.model_dump_json().encode())
            head = store.transition(head, "UNDERSTOOD", snapshot)
        if head.state == "UNDERSTOOD":
            stage = "track"
            assert snapshot.understanding is not None
            prompt = snapshot.tracking_prompt()
            assert prompt is not None
            try:
                tracked, crops = track(
                    root / snapshot.brief.video_path, prompt, adapters.sam, cleanup
                )
            finally:
                _record_cleanup(store, head.job_id, cleanup)
                cleanup.clear()
            origin = Provenance(
                mode=mode,
                stage=stage,
                kind="provider",
                model="sam-3.1",
                capture_id=snapshot.media.normalized_sha256,
            )
            snapshot = snapshot.model_copy(
                update={
                    "track": tracked,
                    "crops": crops,
                    "provenance": (*snapshot.provenance, origin),
                }
            )
            atomic_write(root / "track.json", tracked.model_dump_json().encode())
            head = store.transition(head, "TRACKED", snapshot)
        if head.state == "TRACKED":
            stage = "enrich"
            assert snapshot.understanding is not None
            enrichment = enrich(
                root / snapshot.brief.video_path,
                snapshot.media,
                snapshot.understanding,
                root,
                adapters.image,
                adapters.voice,
                mode,
                language=snapshot.brief.language,
            )
            origin = Provenance(
                mode=mode,
                stage=stage,
                kind="local_fallback" if enrichment.image_fallback else "provider",
                model="muse-image-1.0",
                capture_id=(
                    "synthetic-image" if mode == "fixture" else enrichment.thumbnails[0].sha256
                ),
                reason="Image failure" if enrichment.image_fallback else None,
            )
            snapshot = snapshot.model_copy(
                update={"enrichment": enrichment, "provenance": (*snapshot.provenance, origin)}
            )
            atomic_write(root / "enrichment.json", enrichment.model_dump_json().encode())
            head = store.transition(head, "ENRICHED", snapshot)
        if head.state == "ENRICHED":
            stage = "assemble"
            snapshot = assemble(root, snapshot, head.revision, mode)
            head = store.transition(head, "RENDERED", snapshot)
        if head.state == "RENDERED":
            head = store.transition(head, "AWAITING_APPROVAL", snapshot)
        return head
    except AdLoomError as error:
        store.fail(head, error.error.stage, error.error)
        raise
    except (OSError, subprocess.SubprocessError, ValidationError) as cause:
        code: Literal["E_RENDER_FAILED", "E_API_SCHEMA"] = (
            "E_RENDER_FAILED" if stage == "assemble" else "E_API_SCHEMA"
        )
        stage_error = AdLoomError(code, stage, f"Stage failed ({type(cause).__name__})")
        store.fail(head, stage, stage_error.error)
        raise stage_error from None


def run_file(
    settings: Settings,
    video: Path,
    note_text: str | None,
    region: str,
    budget: int,
    note_audio: Path | None = None,
    destination: str | None = None,
    job_id: str | None = None,
    language: Literal["ko", "en"] = "ko",
) -> JobManifest:
    """Create a job and run it. An audio-only explanation stops at note review."""
    require_live_ready(settings)
    if settings.mode == "live" and destination is None:
        raise AdLoomError("E_INPUT_INVALID", "input", "Live jobs require a destination URL")
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        if not video.is_file() or video.suffix.lower() not in {".mp4", ".mov"}:
            raise AdLoomError("E_INPUT_INVALID", "input", "Select a local MP4 or MOV file")
        if video.stat().st_size > 256 * 1024 * 1024:
            raise AdLoomError("E_INPUT_INVALID", "input", "Video exceeds 256 MiB")
        audio_suffix = note_audio.suffix.lower() if note_audio is not None else ""
        if note_audio is not None and audio_suffix not in NOTE_AUDIO_SUFFIXES:
            raise AdLoomError(
                "E_INPUT_INVALID",
                "input",
                "Explanation audio must be WebM, OGG, M4A, MP4, WAV or MP3",
            )
        job_id = job_id or uuid4().hex
        root = store.path(job_id)
        brief = Brief.model_validate(
            {
                "video_path": "input/normalized.mp4",
                "note_text": note_text,
                "note_audio_path": f"input/note{audio_suffix}" if note_audio is not None else None,
                "region": region,
                "daily_budget_krw": budget,
                "destination_url": destination,
                "language": language,
            }
        )
        (root / "input").mkdir(parents=True)
        try:
            shutil.copyfile(video, root / "input/source.mp4")
            if note_audio is not None:
                if not note_audio.is_file() or note_audio.stat().st_size > 32 * 1024 * 1024:
                    raise AdLoomError(
                        "E_INPUT_INVALID", "input", "Select an explanation audio file up to 32 MiB"
                    )
                shutil.copyfile(note_audio, root / f"input/note{audio_suffix}")
            media = normalize(root / "input/source.mp4", root / brief.video_path)
            head = store.create(brief, media, job_id, mode=settings.mode)
        except BaseException:
            # No job record exists yet; do not leave a copy of the customer's video behind.
            shutil.rmtree(root, ignore_errors=True)
            raise
        return _run(settings, store, head)


def resume_job(settings: Settings, job_id: str) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return _run(settings, store, store.load(job_id))


def inspect_job(settings: Settings, job_id: str) -> dict[str, object]:
    store = JobStore(settings.data_dir)
    head = store.load(job_id)
    snapshot = store.snapshot(head)
    result: dict[str, object] = {
        "job": head.model_dump(mode="json"),
        "snapshot": snapshot.model_dump(mode="json"),
        "notice": (
            "Fixture mode: no model inference or real ads"
            if head.execution_mode == "fixture"
            else "Live mode: model inference and paused Meta ads"
        ),
    }
    warnings_path = store.path(job_id, "cleanup_warnings.json")
    if warnings_path.is_file():
        result["cleanup_warnings"] = json.loads(warnings_path.read_bytes())
    if snapshot.render_plan is not None:
        try:
            subject = make_subject(store, head, snapshot)
            result["content_digest"] = subject.content_digest()
            result["policy_flags"] = [flag.model_dump(mode="json") for flag in subject.policy_flags]
            result["approval_issues"] = list(approval_issues(subject))
        except AdLoomError as error:
            result["approval_error"] = error.error.model_dump(mode="json")
    return result


def approve_job(
    settings: Settings,
    job_id: str,
    actor: str,
    digest: str | None = None,
    channel: Literal["cli", "web"] = "cli",
) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return approve(store, store.load(job_id), actor, channel=channel, expected_digest=digest)


def publish_job(settings: Settings, job_id: str) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        _check_mode(settings, head)
        return publish(store, head, get_adapters(settings, store.path(job_id)).marketing)


def edit_job(
    settings: Settings,
    job_id: str,
    *,
    hook_a: str | None = None,
    hook_b: str | None = None,
    primary_text: str | None = None,
    headline: str | None = None,
    moments: Sequence[int] | None = None,
    product: str | None = None,
) -> JobManifest:
    """Edit a rendered job. Rolls back to the earliest stage the change invalidates."""
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        if head.state not in {"AWAITING_APPROVAL", "APPROVED"} or any(
            store.path(job_id).glob("publish/*.json")
        ):
            raise AdLoomError(
                "E_STATE_CONFLICT", "assemble", "Only unposted, rendered jobs can be edited"
            )
        snapshot = store.snapshot(head)
        assert snapshot.understanding is not None
        selection = snapshot.moment_selection
        if moments is not None:
            count = len(snapshot.understanding.key_moments)
            chosen = tuple(sorted(set(moments)))
            if not chosen or len(chosen) != len(moments) or chosen[0] < 0 or chosen[-1] >= count:
                raise AdLoomError(
                    "E_INPUT_INVALID", "assemble", "Choose at least one of the listed key moments"
                )
            # The full list stays in understanding, so any selection can be undone later.
            selection = () if chosen == tuple(range(count)) else chosen
        prompt = snapshot.track_prompt
        if product is not None:
            product = unicodedata.normalize("NFC", product).strip()
            if not 1 <= len(product) <= 80:
                raise AdLoomError(
                    "E_INPUT_INVALID", "track", "Describe the product in 1 to 80 characters"
                )
            prompt = None if product == snapshot.understanding.sam_prompt else product
        value = snapshot.understanding.model_dump()
        hooks = [hook.model_dump() for hook in snapshot.understanding.hook_candidates]
        for index, text in enumerate((hook_a, hook_b)):
            if text is not None:
                hooks[index]["text"] = text
        value["hook_candidates"] = hooks
        if primary_text is not None:
            value["primary_text"] = primary_text
        if headline is not None:
            value["headline"] = headline
        changed = Understanding.model_validate(value)
        changed = changed.model_copy(update={"policy_flags": check(understanding_fields(changed))})
        reviews = snapshot.claim_reviews
        old = snapshot.understanding
        if (changed.hook_candidates, changed.primary_text, changed.headline) != (
            old.hook_candidates,
            old.primary_text,
            old.headline,
        ):
            # A rejected claim means "this is not true". Rewriting the copy is the owner's fix,
            # so the rejected claims leave the reviewed set; accepted decisions stay.
            rejected = {review.id for review in reviews if review.status == "rejected"}
            changed = changed.model_copy(
                update={"claims": tuple(c for c in changed.claims if c.id not in rejected)}
            )
            reviews = tuple(review for review in reviews if review.id not in rejected)
        rollback: JobState | None = None
        if changed != snapshot.understanding or selection != snapshot.moment_selection:
            rollback = "ENRICHED"
        if prompt != snapshot.track_prompt:
            rollback = "UNDERSTOOD"
        if rollback is None:
            return head
        update: dict[str, object] = {
            "understanding": changed,
            "moment_selection": selection,
            "track_prompt": prompt,
            "variants": (),
            "render_plan": None,
            "approval_subject": None,
            "claim_reviews": reviews,
        }
        if rollback == "UNDERSTOOD":
            update.update({"track": None, "crops": (), "enrichment": None})
        head = store.commit(
            head,
            snapshot.model_copy(update=update),
            revision=head.revision + 1,
            state=rollback,
            last_success_state=rollback,
            approval_ref=None,
        )
        return _run(settings, store, head)


def review_claims(
    settings: Settings, job_id: str, decisions: Mapping[str, str], actor: str
) -> JobManifest:
    """Record the owner's verdict on claims. Same revision, new manifest; approval cleared.

    Videos are not re-rendered. A rejected claim keeps approval blocked until a copy edit
    (edit_job) drops it from the reviewed set.
    """
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        if head.state not in {"AWAITING_APPROVAL", "APPROVED"} or any(
            store.path(job_id).glob("publish/*.json")
        ):
            raise AdLoomError(
                "E_STATE_CONFLICT", "publish", "Only unposted, rendered jobs can be reviewed"
            )
        actor = unicodedata.normalize("NFC", actor).strip()
        if not 1 <= len(actor) <= 80:
            raise AdLoomError("E_INPUT_INVALID", "publish", "Enter who reviewed the claims")
        snapshot = store.snapshot(head)
        _, current = claim_reviews(snapshot)
        known = {claim.id: claim for claim in current}
        if (
            not decisions
            or not set(decisions) <= set(known)
            or not set(decisions.values()) <= {"accepted", "rejected"}
        ):
            raise AdLoomError(
                "E_INPUT_INVALID", "publish", "Mark listed claims as accepted or rejected"
            )
        reviewed = {claim.id: claim for claim in current if claim.status != "pending"}
        for claim_id, status in decisions.items():
            reviewed[claim_id] = ClaimReview.model_validate(
                {**known[claim_id].model_dump(), "status": status, "actor": actor}
            )
        updated = tuple(sorted(reviewed.values(), key=lambda claim: claim.id))
        if updated == snapshot.claim_reviews:
            return head
        return store.commit(
            head,
            snapshot.model_copy(update={"claim_reviews": updated, "approval_subject": None}),
            state="AWAITING_APPROVAL",
            last_success_state="AWAITING_APPROVAL",
            approval_ref=None,
        )


def confirm_note(settings: Settings, job_id: str, text: str) -> JobManifest:
    """Owner-confirmed explanation for a job still waiting on its note."""
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        waiting = head.state == "CREATED" or (
            head.state == "FAILED"
            and head.failed_stage == "input"
            and head.last_success_state == "CREATED"
        )
        if head.note_status == "CONFIRMED" or not waiting:
            raise AdLoomError(
                "E_STATE_CONFLICT", "input", "This job's explanation is already confirmed"
            )
        snapshot = store.snapshot(head)
        try:
            brief = Brief.model_validate({**snapshot.brief.model_dump(), "note_text": text})
        except ValidationError:
            raise AdLoomError(
                "E_INPUT_INVALID", "input", "Explanation must be 1 to 200 characters"
            ) from None
        if brief.note_text is None or not brief.note_text.strip():
            raise AdLoomError("E_INPUT_INVALID", "input", "Explanation must not be blank")
        atomic_write(store.path(job_id, "brief.json"), brief.model_dump_json().encode())
        head = store.commit(
            head,
            snapshot.model_copy(update={"brief": brief}),
            state="CREATED",
            note_status="CONFIRMED",
            failed_stage=None,
            pending_stage=None,
            error=None,
        )
        return _run(settings, store, head)


def abandon_publish(settings: Settings, job_id: str, operation_key: str, actor: str) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return abandon(store, store.load(job_id), operation_key, actor)


def delete_job(settings: Settings, job_id: str) -> None:
    """Remove a local job. Refused while a publish request outcome is still unknown."""
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        if head.run_state in {"RUNNING", "CANCEL_REQUESTED"}:
            raise AdLoomError("E_JOB_BUSY", "input", "The job is running")
        if any(unresolved(operation) for operation in operations(store, job_id)):
            raise AdLoomError(
                "E_STATE_CONFLICT",
                "publish",
                "A publish request outcome is unknown; abandon it before deleting",
            )
        shutil.rmtree(store.path(job_id))
