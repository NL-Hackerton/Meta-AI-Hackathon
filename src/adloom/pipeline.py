"""Shared synchronous commands for the local, explicitly offline AdLoom workflow."""

import shutil
import subprocess
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from adloom.adapters.base import get_adapters
from adloom.config import AdLoomError, Settings
from adloom.jobs import JobStore, atomic_write
from adloom.schemas import Brief, JobManifest, Provenance, Stage, Understanding
from adloom.stages.assemble import assemble
from adloom.stages.enrich import enrich
from adloom.stages.input import fill_note, normalize
from adloom.stages.publish import approve, fixture_publish_plan, make_subject, publish
from adloom.stages.track import track
from adloom.stages.understand import understand


def _run(settings: Settings, store: JobStore, head: JobManifest) -> JobManifest:
    root = store.path(head.job_id)
    adapters = get_adapters(settings, root)
    if head.state == "FAILED":
        if head.failed_stage == "publish":
            return publish(store, head, adapters.marketing)
        head = store.resume(head)
    stage: Stage = "input"
    try:
        snapshot = store.snapshot(head)
        if head.state == "CREATED":
            brief = fill_note(snapshot.brief, root, adapters.voice)
            stage = "understand"
            result = understand(root / "input/source.mp4", brief.note_text or "", brief.language, adapters.spark)
            if result.source_duration_us != snapshot.media.duration_us:
                raise AdLoomError("E_API_SCHEMA", stage, "Fixture duration differs from normalized video")
            origin = Provenance(mode="fixture", stage=stage, kind="provider", model="muse-spark-1.3",
                                capture_id=snapshot.media.source_sha256)
            snapshot = snapshot.model_copy(update={"brief": brief, "understanding": result,
                                                    "provenance": (*snapshot.provenance, origin)})
            snapshot = snapshot.model_copy(update={"publish_plan": fixture_publish_plan(snapshot)})
            atomic_write(root / "understanding.json", result.model_dump_json().encode())
            head = store.transition(head, "UNDERSTOOD", snapshot)
        if head.state == "UNDERSTOOD":
            stage = "track"
            assert snapshot.understanding is not None
            tracked, crops = track(root / snapshot.brief.video_path, snapshot.understanding.sam_prompt, adapters.sam)
            origin = Provenance(mode="fixture", stage=stage, kind="provider", model="sam-3.1",
                                capture_id=snapshot.media.normalized_sha256)
            snapshot = snapshot.model_copy(update={"track": tracked, "crops": crops,
                                                    "provenance": (*snapshot.provenance, origin)})
            atomic_write(root / "track.json", tracked.model_dump_json().encode())
            head = store.transition(head, "TRACKED", snapshot)
        if head.state == "TRACKED":
            stage = "enrich"
            assert snapshot.understanding is not None
            enrichment = enrich(root / snapshot.brief.video_path, snapshot.media,
                                snapshot.understanding, root, adapters.image, adapters.voice)
            origin = Provenance(mode="fixture", stage=stage,
                                kind="local_fallback" if enrichment.image_fallback else "provider",
                                model="muse-image-1.0", capture_id="synthetic-image",
                                reason="Image failure" if enrichment.image_fallback else None)
            snapshot = snapshot.model_copy(update={"enrichment": enrichment,
                                                    "provenance": (*snapshot.provenance, origin)})
            atomic_write(root / "enrichment.json", enrichment.model_dump_json().encode())
            head = store.transition(head, "ENRICHED", snapshot)
        if head.state == "ENRICHED":
            stage = "assemble"
            snapshot = assemble(root, snapshot, head.revision)
            head = store.transition(head, "RENDERED", snapshot)
        if head.state == "RENDERED":
            head = store.transition(head, "AWAITING_APPROVAL", snapshot)
        return head
    except AdLoomError as error:
        store.fail(head, error.error.stage, error.error)
        raise
    except (OSError, subprocess.SubprocessError, ValidationError) as cause:
        code: Literal["E_RENDER_FAILED", "E_API_SCHEMA"] = "E_RENDER_FAILED" if stage == "assemble" else "E_API_SCHEMA"
        stage_error = AdLoomError(code, stage, f"Stage failed ({type(cause).__name__})")
        store.fail(head, stage, stage_error.error)
        raise stage_error from None


def run_file(
    settings: Settings, video: Path, note_text: str | None, region: str, budget: int,
    note_audio: Path | None = None, destination: str | None = None,
) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        if not video.is_file() or video.suffix.lower() not in {".mp4", ".mov"}:
            raise AdLoomError("E_INPUT_INVALID", "input", "Select a local MP4 or MOV file")
        if video.stat().st_size > 256*1024*1024:
            raise AdLoomError("E_INPUT_INVALID", "input", "Video exceeds 256 MiB")
        job_id = uuid4().hex
        root = store.path(job_id)
        brief = Brief.model_validate({
            "video_path": "input/normalized.mp4", "note_text": note_text,
            "note_audio_path": "input/note.wav" if note_audio is not None else None,
            "region": region, "daily_budget_krw": budget, "destination_url": destination,
        })
        (root / "input").mkdir(parents=True)
        shutil.copyfile(video, root / "input/source.mp4")
        if note_audio is not None:
            if not note_audio.is_file() or note_audio.stat().st_size > 32*1024*1024:
                raise AdLoomError("E_INPUT_INVALID", "input", "Select an explanation audio file up to 32 MiB")
            shutil.copyfile(note_audio, root / "input/note.wav")
        media = normalize(root / "input/source.mp4", root / brief.video_path)
        head = store.create(brief, media, job_id)
        return _run(settings, store, head)


def resume_job(settings: Settings, job_id: str) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return _run(settings, store, store.load(job_id))


def inspect_job(settings: Settings, job_id: str) -> dict[str, object]:
    store = JobStore(settings.data_dir)
    head = store.load(job_id)
    snapshot = store.snapshot(head)
    result: dict[str, object] = {"job": head.model_dump(mode="json"), "snapshot": snapshot.model_dump(mode="json"),
                                 "notice": "Fixture mode: no model inference or real ads"}
    if snapshot.render_plan is not None:
        try:
            result["content_digest"] = make_subject(store, head, snapshot).content_digest()
        except AdLoomError as error:
            result["approval_error"] = error.error.model_dump(mode="json")
    return result


def approve_job(settings: Settings, job_id: str, actor: str, digest: str | None = None) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return approve(store, store.load(job_id), actor, expected_digest=digest)


def publish_job(settings: Settings, job_id: str) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        return publish(store, store.load(job_id), get_adapters(settings, store.path(job_id)).marketing)


def edit_job(
    settings: Settings, job_id: str, *, hook_a: str | None = None, hook_b: str | None = None,
    primary_text: str | None = None, headline: str | None = None,
) -> JobManifest:
    store = JobStore(settings.data_dir)
    with store.execution_lock():
        head = store.load(job_id)
        if head.state not in {"AWAITING_APPROVAL", "APPROVED"} or any(store.path(job_id).glob("publish/*.json")):
            raise AdLoomError("E_STATE_CONFLICT", "assemble", "Only unposted, rendered jobs can be edited")
        snapshot = store.snapshot(head)
        assert snapshot.understanding is not None
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
        if changed == snapshot.understanding:
            return head
        updated = snapshot.model_copy(update={"understanding": changed, "variants": (),
                                              "render_plan": None, "approval_subject": None})
        head = store.commit(head, updated, revision=head.revision+1, state="ENRICHED",
                            last_success_state="ENRICHED", approval_ref=None)
        return _run(settings, store, head)
