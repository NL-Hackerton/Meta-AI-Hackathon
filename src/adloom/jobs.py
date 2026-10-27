"""Atomic local job storage. Application commands serialize with execution_lock."""

import fcntl
import hashlib
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from adloom.config import AdLoomError
from adloom.schemas import (
    ApprovalSubject,
    ArtifactRef,
    Brief,
    CropPlan,
    DomainModel,
    EnrichResult,
    ErrorDetail,
    JobManifest,
    JobState,
    MediaInfo,
    Provenance,
    PublishPlan,
    PublishResult,
    RenderedVariant,
    RenderPlan,
    Stage,
    TrackResult,
    Understanding,
)

STATES: tuple[JobState, ...] = (
    "CREATED",
    "UNDERSTOOD",
    "TRACKED",
    "ENRICHED",
    "RENDERED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "PUBLISHED_PAUSED",
)


class Snapshot(DomainModel):
    brief: Brief
    media: MediaInfo
    understanding: Understanding | None = None
    track: TrackResult | None = None
    crops: tuple[CropPlan, ...] = ()
    enrichment: EnrichResult | None = None
    render_plan: RenderPlan | None = None
    variants: tuple[RenderedVariant, ...] = ()
    provenance: tuple[Provenance, ...] = ()
    publish_plan: PublishPlan | None = None
    approval_subject: ApprovalSubject | None = None
    publish_result: PublishResult | None = None


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def allowed_transition(source: JobState, target: JobState) -> bool:
    if target == "FAILED":
        return source != "FAILED"
    if source in {"AWAITING_APPROVAL", "APPROVED"} and target == "RENDERED":
        return True
    return source in STATES[:-1] and target == STATES[STATES.index(source) + 1]


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        (self.root / "jobs").mkdir(parents=True, exist_ok=True)

    @contextmanager
    def execution_lock(self) -> Iterator[None]:
        with (self.root / ".run.lock").open("a+b") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise AdLoomError("E_JOB_BUSY", "input", "Another command is running") from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def path(self, job_id: str, relative: str = "") -> Path:
        if re.fullmatch(r"[a-f0-9]{32}", job_id) is None:
            raise AdLoomError("E_INPUT_INVALID", "input", "Invalid job ID")
        base = (self.root / "jobs" / job_id).resolve()
        target = (base / relative).resolve()
        if not base.is_relative_to(self.root / "jobs") or not target.is_relative_to(base):
            raise AdLoomError("E_INPUT_INVALID", "input", "Path escapes the job directory")
        return target

    def load(self, job_id: str) -> JobManifest:
        return JobManifest.model_validate_json(self.path(job_id, "job.json").read_bytes())

    def snapshot(self, head: JobManifest) -> Snapshot:
        path = self.path(head.job_id, head.manifest_ref.path)
        if file_hash(path) != head.manifest_ref.sha256:
            raise AdLoomError("E_STATE_CONFLICT", "input", "Manifest digest mismatch")
        return Snapshot.model_validate_json(path.read_bytes())

    def create(self, brief: Brief, media: MediaInfo, job_id: str | None = None) -> JobManifest:
        identifier = job_id or uuid4().hex
        if self.path(identifier, "job.json").exists():
            raise AdLoomError("E_STATE_CONFLICT", "input", "Job already exists")
        now = datetime.now(UTC)
        snapshot = Snapshot(brief=brief, media=media)
        ref = self._snapshot_ref(identifier, 1, 1, snapshot)
        head = JobManifest(
            job_id=identifier,
            revision=1,
            manifest_seq=1,
            execution_mode="fixture",
            state="CREATED",
            last_success_state="CREATED",
            run_state="IDLE",
            note_status="CONFIRMED" if brief.note_text else "AUDIO_PENDING",
            manifest_ref=ref,
            created_at=now,
            updated_at=now,
        )
        atomic_write(self.path(identifier, "brief.json"), brief.model_dump_json().encode())
        atomic_write(self.path(identifier, "job.json"), head.model_dump_json().encode())
        return head

    def _snapshot_ref(self, job_id: str, revision: int, seq: int, data: Snapshot) -> ArtifactRef:
        relative = f"revisions/r{revision:06d}/manifests/m{seq:06d}.json"
        payload = data.model_dump_json().encode()
        atomic_write(self.path(job_id, relative), payload)
        return ArtifactRef(path=relative, sha256=hashlib.sha256(payload).hexdigest())

    def commit(self, head: JobManifest, snapshot: Snapshot, **changes: object) -> JobManifest:
        current = self.load(head.job_id)
        if (current.revision, current.manifest_seq) != (head.revision, head.manifest_seq):
            raise AdLoomError(
                "E_REVISION_CONFLICT", "input", "Job changed; reload before continuing"
            )
        values = head.model_dump()
        values.update(changes)
        values["manifest_seq"] = head.manifest_seq + 1
        values["updated_at"] = datetime.now(UTC)
        # Validate state before creating the immutable snapshot.
        candidate = JobManifest.model_validate(values)
        ref = self._snapshot_ref(head.job_id, candidate.revision, candidate.manifest_seq, snapshot)
        values["manifest_ref"] = ref
        result = JobManifest.model_validate(values)
        atomic_write(self.path(head.job_id, "job.json"), result.model_dump_json().encode())
        return result

    def transition(
        self,
        head: JobManifest,
        target: JobState,
        snapshot: Snapshot,
        approval_ref: ArtifactRef | None = None,
    ) -> JobManifest:
        if not allowed_transition(head.state, target) or target == "FAILED":
            raise AdLoomError("E_STATE_CONFLICT", "input", "Illegal state transition")
        required = {
            "UNDERSTOOD": snapshot.understanding is not None,
            "TRACKED": snapshot.track is not None and len(snapshot.crops) == 3,
            "ENRICHED": snapshot.enrichment is not None,
            "RENDERED": len(snapshot.variants) == 6 and snapshot.render_plan is not None,
            "AWAITING_APPROVAL": len(snapshot.variants) == 6,
            "APPROVED": approval_ref is not None and snapshot.approval_subject is not None,
            "PUBLISHED_PAUSED": snapshot.publish_result is not None,
        }
        if not required.get(target, False):
            raise AdLoomError("E_STATE_CONFLICT", "input", "Required stage artifacts are missing")
        reference = approval_ref or head.approval_ref
        if target == "RENDERED":
            reference = None
        return self.commit(
            head,
            snapshot,
            state=target,
            last_success_state=target,
            approval_ref=reference,
            failed_stage=None,
            error=None,
            pending_stage=None,
            note_status="CONFIRMED",
        )

    def fail(self, head: JobManifest, stage: Stage, error: ErrorDetail) -> JobManifest:
        return self.commit(
            head,
            self.snapshot(head),
            state="FAILED",
            failed_stage=stage,
            pending_stage=stage,
            error=error,
            run_state="IDLE",
            active_run_id=None,
        )

    def resume(self, head: JobManifest) -> JobManifest:
        if head.state != "FAILED":
            raise AdLoomError("E_STATE_CONFLICT", "input", "Only failed jobs can resume")
        return self.commit(
            head,
            self.snapshot(head),
            state=head.last_success_state,
            failed_stage=None,
            error=None,
            pending_stage=None,
        )
