"""FastAPI app: fixture jobs, review media, approval and paused publishing.

Every write goes through adloom.pipeline so the web path keeps the CLI's locks,
approval digest checks and PAUSED-only publishing.
"""

import os
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import RequestResponseEndpoint

from adloom.config import FONT_PATH, AdLoomError, Settings
from adloom.jobs import JobStore, Snapshot
from adloom.pipeline import (
    NOTE_AUDIO_SUFFIXES,
    abandon_publish,
    approve_job,
    confirm_note,
    delete_job,
    edit_job,
    inspect_job,
    publish_job,
    resume_job,
    run_file,
)
from adloom.schemas import ApprovalRecord, ErrorCode, JobManifest
from adloom.stages.publish import operations, unresolved
from adloom.web.profile import Profile, load_profile, save_profile

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
MAX_AUDIO_BYTES = 32 * 1024 * 1024
SOURCE_VIDEO = "input/normalized.mp4"
META_PERMISSIONS = ("ads_management", "pages_read_engagement")
MAX_BODY_BYTES = 257 * 1024 * 1024
LOOPBACK_HOSTS = ("127.0.0.1", "localhost")
REQUEST_HEADER = "x-adloom-request"
MEDIA_TYPES = {".mp4": "video/mp4", ".png": "image/png"}
MEDIA_ROOTS = ("renders", "enrichment", "images")
CONFLICT_CODES: frozenset[ErrorCode] = frozenset(
    {
        "E_APPROVAL_REQUIRED",
        "E_JOB_BUSY",
        "E_POLICY_BLOCK",
        "E_REVISION_CONFLICT",
        "E_STATE_CONFLICT",
    }
)


class ApproveBody(BaseModel):
    actor: str
    digest: str


class EditBody(BaseModel):
    hook_a: str | None = None
    hook_b: str | None = None
    primary_text: str | None = None
    headline: str | None = None
    moments: list[int] | None = None
    product: str | None = None


class NoteBody(BaseModel):
    text: str


class AbandonBody(BaseModel):
    operation_key: str
    actor: str


def _error(status: int, code: ErrorCode, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "detail": detail}})


def _file_url(job_id: str, relative: str) -> str:
    return f"/api/jobs/{job_id}/files/{relative}"


async def _save_upload(upload: UploadFile, target: Path, limit: int, label: str) -> None:
    size = 0
    with target.open("wb") as stream:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                raise AdLoomError(
                    "E_INPUT_INVALID", "input", f"{label} exceeds {limit // (1024 * 1024)} MiB"
                )
            stream.write(chunk)


def _tracking(snapshot: Snapshot) -> dict[str, object] | None:
    tracked = snapshot.track
    if tracked is None:
        return None
    return {
        "source_width": tracked.source_width,
        "source_height": tracked.source_height,
        "fps": tracked.fps.model_dump(),
        "frame_count": tracked.frame_count,
        "coverage": tracked.coverage,
        "prompt": snapshot.tracking_prompt(),
        "boxes": [None if box is None else [box.x, box.y, box.w, box.h] for box in tracked.boxes],
        "crops": {
            crop.aspect: [[rect.x, rect.y, rect.w, rect.h] for rect in crop.rects]
            for crop in snapshot.crops
        },
        "degraded": {crop.aspect: crop.degraded for crop in snapshot.crops},
    }


def _moments(snapshot: Snapshot) -> list[dict[str, object]]:
    if snapshot.understanding is None:
        return []
    selection = snapshot.moment_selection
    return [
        {
            "index": index,
            "start_us": moment.start_us,
            "end_us": moment.end_us,
            "reason": moment.reason,
            "selected": not selection or index in selection,
        }
        for index, moment in enumerate(snapshot.understanding.key_moments)
    ]


def _notification(
    head: JobManifest, product: str | None, unknown: bool
) -> dict[str, object] | None:
    name = product or "Your ad"
    kind: str
    if head.state == "CREATED" and head.note_status == "REVIEW_REQUIRED":
        kind, title, detail = (
            "note_review",
            "Check what you said",
            "Check the transcript of your voice note before we make the ads.",
        )
    elif (
        head.state == "FAILED" and head.failed_stage == "input" and head.note_status != "CONFIRMED"
    ):
        kind, title, detail = (
            "note_review",
            "Type what the video is about",
            "We could not read your voice note. Type a short description to continue.",
        )
    elif head.state == "AWAITING_APPROVAL":
        kind, title, detail = (
            "ready",
            f"{name} is ready for review",
            "Six videos are ready. Review and approve to publish as paused ads.",
        )
    elif head.state == "PUBLISHED_PAUSED":
        kind, title, detail = (
            "published",
            f"{name} published as paused",
            "Two ads were created and stay paused until you turn them on.",
        )
    elif head.state == "FAILED" and unknown:
        kind, title, detail = (
            "unknown",
            "Publish result unknown",
            "A publish request may or may not have reached Meta. It will not be resent.",
        )
    elif head.state == "FAILED":
        kind, title = "failed", f"{name}: a step failed"
        detail = head.error.detail if head.error is not None else "A step failed."
    else:
        return None
    return {
        "id": f"{head.job_id}.{head.revision}.{head.manifest_seq}.{kind}",
        "job_id": head.job_id,
        "kind": kind,
        "title": title,
        "detail": detail,
        "at": head.updated_at.isoformat(),
    }


def create_app(settings: Settings, allowed_hosts: tuple[str, ...] = LOOPBACK_HOSTS) -> FastAPI:
    app = FastAPI(title="AdLoom", docs_url=None, redoc_url=None, openapi_url=None)
    store = JobStore(settings.data_dir)

    @app.middleware("http")
    async def boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        # No session yet: the app is a loopback tool. Host checks stop DNS rebinding; the
        # custom header forces a CORS preflight that this app never grants, so other sites
        # cannot submit uploads, approvals or publish requests through the browser.
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]")
        if host not in allowed_hosts:
            return _error(403, "E_INPUT_INVALID", "Host not allowed")
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if request.headers.get(REQUEST_HEADER) != "1" or (
                origin is not None and origin.split("://", 1)[-1] != request.headers.get("host")
            ):
                return _error(403, "E_INPUT_INVALID", "Cross-site request refused")
            length = request.headers.get("content-length")
            if length is not None and (not length.isdigit() or int(length) > MAX_BODY_BYTES):
                return _error(413, "E_INPUT_INVALID", "Request body exceeds 257 MiB")
        return await call_next(request)

    @app.exception_handler(AdLoomError)
    async def adloom_error(_: Request, error: AdLoomError) -> JSONResponse:
        status = 422 if error.error.code == "E_INPUT_INVALID" else 502
        if error.error.code in CONFLICT_CODES:
            status = 409
        return JSONResponse(status_code=status, content={"error": error.error.model_dump()})

    @app.exception_handler(ValidationError)
    async def invalid(_: Request, __: ValidationError) -> JSONResponse:
        return _error(422, "E_INPUT_INVALID", "Input violates the data contract")

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error(422, "E_INPUT_INVALID", "Request is missing or has invalid fields")

    @app.exception_handler(FileNotFoundError)
    async def missing(_: Request, __: FileNotFoundError) -> JSONResponse:
        return _error(404, "E_INPUT_INVALID", "Job not found")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", media_type="text/html")

    @app.get("/assets/noto-sans-kr.ttf")
    def font() -> FileResponse:
        return FileResponse(FONT_PATH, media_type="font/ttf")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return {
            "mode": settings.mode,
            "live": False,
            "spark_model": settings.spark_model,
            "notice": "Fixture mode: no model inference or real ads",
            "meta": {
                "connected": False,
                "detail": "Not connected. Connecting a Meta ad account needs human approval "
                "and live mode, which this local fixture app does not enable.",
                "permissions": list(META_PERMISSIONS),
            },
            "model_api": {"key_present": bool(os.environ.get("MODEL_API_KEY"))},
            "busy": store.busy(),
        }

    @app.get("/api/profile")
    def get_profile() -> dict[str, object]:
        profile = load_profile(store.root)
        return {"profile": None if profile is None else profile.model_dump(mode="json")}

    @app.put("/api/profile")
    def put_profile(body: Profile) -> dict[str, object]:
        return {"profile": save_profile(store.root, body).model_dump(mode="json")}

    def observed(head: JobManifest, busy: bool) -> dict[str, object]:
        # A RUNNING head without a lock holder was left by a process that stopped mid-run.
        value = head.model_dump(mode="json")
        if head.run_state in {"RUNNING", "CANCEL_REQUESTED"} and not busy:
            value["run_state"] = "INTERRUPTED"
        return value

    def summary(job_id: str, busy: bool) -> dict[str, object]:
        head = store.load(job_id)
        result: dict[str, object] = {
            **observed(head, busy),
            "product_name": None,
            "hooks": [],
            "published_ads": [],
        }
        try:
            snapshot = store.snapshot(head)
        except AdLoomError:
            return result
        if snapshot.understanding is not None:
            result["product_name"] = snapshot.understanding.product_name
            result["headline"] = snapshot.understanding.headline
            hooks = (
                snapshot.render_plan.hooks
                if snapshot.render_plan is not None
                else snapshot.understanding.hook_candidates[:2]
            )
            result["hooks"] = [hook.model_dump(mode="json") for hook in hooks]
        if head.state == "PUBLISHED_PAUSED" and snapshot.publish_result is not None:
            videos = {v.hook_id: v.path for v in snapshot.variants if v.aspect == "9:16"}
            result["published_ads"] = [
                {
                    "hook_id": ad.hook_id,
                    "ad_id": ad.ad_id,
                    "configured_status": ad.configured_status,
                    "video_url": _file_url(job_id, videos[ad.hook_id])
                    if ad.hook_id in videos
                    else None,
                }
                for ad in snapshot.publish_result.ads
            ]
        if snapshot.enrichment is not None:
            result["thumbnail_url"] = _file_url(job_id, snapshot.enrichment.thumbnails[0].path)
        result["region"] = snapshot.brief.region
        result["daily_budget_krw"] = snapshot.brief.daily_budget_krw
        return result

    def job_ids() -> list[str]:
        return [path.parent.name for path in (store.root / "jobs").glob("*/job.json")]

    @app.get("/api/jobs")
    def jobs() -> list[dict[str, object]]:
        busy = store.busy()
        items: list[dict[str, object]] = []
        for job_id in job_ids():
            try:
                items.append(summary(job_id, busy))
            except FileNotFoundError:
                continue  # deleted while listing
        return sorted(items, key=lambda item: str(item["created_at"]), reverse=True)

    @app.get("/api/notifications")
    def notifications() -> list[dict[str, object]]:
        found: list[dict[str, object]] = []
        for job_id in job_ids():
            product: str | None = None
            try:
                head = store.load(job_id)
                unknown = any(unresolved(operation) for operation in operations(store, job_id))
                understanding = store.snapshot(head).understanding
                product = understanding.product_name if understanding is not None else None
            except FileNotFoundError:
                continue  # deleted while listing
            except AdLoomError:
                pass
            item = _notification(head, product, unknown)
            if item is not None:
                found.append(item)
        return sorted(found, key=lambda item: str(item["at"]), reverse=True)

    @app.post("/api/jobs")
    async def create(
        video: Annotated[UploadFile, File()],
        region: Annotated[str, Form()],
        budget: Annotated[int, Form()],
        note: Annotated[str | None, Form()] = None,
        note_audio: Annotated[UploadFile | None, File()] = None,
        destination: Annotated[str | None, Form()] = None,
        language: Annotated[Literal["ko", "en"], Form()] = "ko",
    ) -> dict[str, object]:
        suffix = PurePosixPath(video.filename or "").suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise AdLoomError("E_INPUT_INVALID", "input", "Select an MP4 or MOV video")
        note = note or None
        audio_suffix = ""
        if note_audio is not None:
            audio_suffix = PurePosixPath(note_audio.filename or "").suffix.lower()
            if audio_suffix not in NOTE_AUDIO_SUFFIXES:
                raise AdLoomError(
                    "E_INPUT_INVALID",
                    "input",
                    "Explanation audio must be WebM, OGG, M4A, MP4, WAV or MP3",
                )
        elif note is None:
            raise AdLoomError("E_INPUT_INVALID", "input", "Describe the product or record a note")
        uploads = store.root / "uploads"
        uploads.mkdir(exist_ok=True)
        target = uploads / f"{uuid4().hex}{suffix}"
        audio = uploads / f"{uuid4().hex}{audio_suffix}" if note_audio is not None else None
        job_id = uuid4().hex
        try:
            await _save_upload(video, target, MAX_UPLOAD_BYTES, "Video")
            if note_audio is not None and audio is not None:
                await _save_upload(note_audio, audio, MAX_AUDIO_BYTES, "Explanation audio")
            head = await run_in_threadpool(
                run_file,
                settings,
                target,
                note,
                region,
                budget,
                audio,
                destination or None,
                job_id,
                language,
            )
        except AdLoomError:
            # An audio-only job whose transcript failed waits for the owner to type the note.
            if note is not None or not store.path(job_id, "job.json").is_file():
                raise
            head = store.load(job_id)
            if head.state != "FAILED" or head.note_status == "CONFIRMED":
                raise
        finally:
            target.unlink(missing_ok=True)
            if audio is not None:
                audio.unlink(missing_ok=True)
        return head.model_dump(mode="json")

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str) -> dict[str, object]:
        result = inspect_job(settings, job_id)
        head = store.load(job_id)
        snapshot = store.snapshot(head)
        result["job"] = observed(head, store.busy())
        result["source_url"] = (
            _file_url(job_id, SOURCE_VIDEO) if store.path(job_id, SOURCE_VIDEO).is_file() else None
        )
        result["note_proposal"] = snapshot.note_proposal
        result["moments"] = _moments(snapshot)
        result["tracking"] = _tracking(snapshot)
        result["variants"] = [
            {**variant.model_dump(mode="json"), "url": _file_url(job_id, variant.path)}
            for variant in snapshot.variants
        ]
        result["thumbnails"] = (
            [
                {"aspect": image.aspect, "url": _file_url(job_id, image.path)}
                for image in snapshot.enrichment.thumbnails
            ]
            if snapshot.enrichment is not None
            else []
        )
        result["degraded"] = any(crop.degraded for crop in snapshot.crops)
        result["clipped"] = any(crop.clipped_frames for crop in snapshot.crops)
        result.setdefault(
            "policy_flags",
            [flag.model_dump(mode="json") for flag in snapshot.understanding.policy_flags]
            if snapshot.understanding is not None
            else [],
        )
        result.setdefault("approval_issues", [])
        result["approval"] = None
        if head.approval_ref is not None:
            record = store.path(job_id, head.approval_ref.path)
            if record.is_file():
                approval = ApprovalRecord.model_validate_json(record.read_bytes())
                result["approval"] = approval.model_dump(mode="json")
        result["operations"] = [
            {**operation.model_dump(mode="json"), "operation_key": operation.operation_key}
            for operation in operations(store, job_id)
        ]
        return result

    @app.get("/api/jobs/{job_id}/files/{relative:path}")
    def media(job_id: str, relative: str) -> Response:
        parts = PurePosixPath(relative).parts
        media_type = MEDIA_TYPES.get(PurePosixPath(relative).suffix.lower())
        allowed = relative == SOURCE_VIDEO or (parts and parts[0] in MEDIA_ROOTS)
        if not allowed or ".." in parts or media_type is None:
            return _error(404, "E_INPUT_INVALID", "File not available for review")
        path = store.path(job_id, relative)
        if not path.is_file():
            return _error(404, "E_INPUT_INVALID", "File not found")
        return FileResponse(path, media_type=media_type)

    @app.post("/api/jobs/{job_id}/approve")
    def approve(job_id: str, body: ApproveBody) -> dict[str, object]:
        head = approve_job(settings, job_id, body.actor, body.digest, channel="web")
        return head.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/publish")
    def publish(job_id: str) -> dict[str, object]:
        return publish_job(settings, job_id).model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/edit")
    def edit(job_id: str, body: EditBody) -> dict[str, object]:
        head = edit_job(
            settings,
            job_id,
            hook_a=body.hook_a,
            hook_b=body.hook_b,
            primary_text=body.primary_text,
            headline=body.headline,
            moments=body.moments,
            product=body.product,
        )
        return head.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/confirm-note")
    def confirm(job_id: str, body: NoteBody) -> dict[str, object]:
        return confirm_note(settings, job_id, body.text).model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/publish/abandon")
    def abandon(job_id: str, body: AbandonBody) -> dict[str, object]:
        head = abandon_publish(settings, job_id, body.operation_key, body.actor)
        return head.model_dump(mode="json")

    @app.delete("/api/jobs/{job_id}")
    def delete(job_id: str) -> dict[str, object]:
        delete_job(settings, job_id)
        return {"deleted": job_id}

    @app.post("/api/jobs/{job_id}/resume")
    def resume(job_id: str) -> dict[str, object]:
        return resume_job(settings, job_id).model_dump(mode="json")

    return app
