"""FastAPI app: fixture jobs, review media, approval and paused publishing.

Every write goes through adloom.pipeline so the web path keeps the CLI's locks,
approval digest checks and PAUSED-only publishing.
"""

from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.middleware.base import RequestResponseEndpoint

from adloom.config import FONT_PATH, AdLoomError, Settings
from adloom.jobs import JobStore
from adloom.pipeline import (
    approve_job,
    edit_job,
    inspect_job,
    publish_job,
    resume_job,
    run_file,
)
from adloom.schemas import ApprovalRecord, ErrorCode, PublishOperation

STATIC = Path(__file__).resolve().parent / "static"
MAX_UPLOAD_BYTES = 256 * 1024 * 1024
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


def _error(status: int, code: ErrorCode, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "detail": detail}})


def _file_url(job_id: str, relative: str) -> str:
    return f"/api/jobs/{job_id}/files/{relative}"


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

    @app.get("/api/status")
    def status() -> dict[str, object]:
        return {
            "mode": settings.mode,
            "live": False,
            "spark_model": settings.spark_model,
            "notice": "Fixture mode: no model inference or real ads",
        }

    def summary(job_id: str) -> dict[str, object]:
        head = store.load(job_id)
        result: dict[str, object] = {**head.model_dump(mode="json"), "product_name": None}
        try:
            snapshot = store.snapshot(head)
        except AdLoomError:
            return result
        if snapshot.understanding is not None:
            result["product_name"] = snapshot.understanding.product_name
            result["headline"] = snapshot.understanding.headline
        if snapshot.enrichment is not None:
            result["thumbnail_url"] = _file_url(job_id, snapshot.enrichment.thumbnails[0].path)
        result["region"] = snapshot.brief.region
        result["daily_budget_krw"] = snapshot.brief.daily_budget_krw
        return result

    @app.get("/api/jobs")
    def jobs() -> list[dict[str, object]]:
        found = [path.parent.name for path in (store.root / "jobs").glob("*/job.json")]
        items = [summary(job_id) for job_id in found]
        return sorted(items, key=lambda item: str(item["created_at"]), reverse=True)

    @app.post("/api/jobs")
    async def create(
        video: Annotated[UploadFile, File()],
        note: Annotated[str, Form()],
        region: Annotated[str, Form()],
        budget: Annotated[int, Form()],
        destination: Annotated[str | None, Form()] = None,
    ) -> dict[str, object]:
        suffix = PurePosixPath(video.filename or "").suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise AdLoomError("E_INPUT_INVALID", "input", "Select an MP4 or MOV video")
        uploads = store.root / "uploads"
        uploads.mkdir(exist_ok=True)
        target = uploads / f"{uuid4().hex}{suffix}"
        try:
            size = 0
            with target.open("wb") as stream:
                while chunk := await video.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise AdLoomError("E_INPUT_INVALID", "input", "Video exceeds 256 MiB")
                    stream.write(chunk)
            head = await run_in_threadpool(
                run_file, settings, target, note, region, budget, None, destination or None
            )
        finally:
            target.unlink(missing_ok=True)
        return head.model_dump(mode="json")

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str) -> dict[str, object]:
        result = inspect_job(settings, job_id)
        head = store.load(job_id)
        snapshot = store.snapshot(head)
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
            {
                **operation.model_dump(mode="json"),
                "operation_key": operation.operation_key,
            }
            for operation in sorted(
                (
                    PublishOperation.model_validate_json(path.read_bytes())
                    for path in store.path(job_id, "publish").glob("*.json")
                ),
                key=lambda operation: operation.operation_key,
            )
        ]
        return result

    @app.get("/api/jobs/{job_id}/files/{relative:path}")
    def media(job_id: str, relative: str) -> Response:
        parts = PurePosixPath(relative).parts
        media_type = MEDIA_TYPES.get(PurePosixPath(relative).suffix.lower())
        if not parts or parts[0] not in MEDIA_ROOTS or ".." in parts or media_type is None:
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
        )
        return head.model_dump(mode="json")

    @app.post("/api/jobs/{job_id}/resume")
    def resume(job_id: str) -> dict[str, object]:
        return resume_job(settings, job_id).model_dump(mode="json")

    return app
