"""Shared HTTP plumbing for the Meta Model API live adapters.

Nothing in this module reads the environment or decides whether live execution
is allowed; that gate stays in ``adloom.config``. Callers pass the API key and,
in tests, a client built with ``build_client(transport=httpx.MockTransport(...))``.
"""

import json
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn

import httpx
from httpx_sse import EventSource

from adloom.config import AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import ErrorCode, Stage

BASE_URL = "https://api.meta.ai/v1"
STANDARD_MODELS = frozenset(
    {"muse-spark-1.3", "sam-3.1", "muse-image-1.0", "muse-voice-transcribe-1.0"}
)
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0)
MAX_UPLOAD_BYTES = 1_073_741_824
MAX_JSON_BYTES = 33_554_432
MAX_ERROR_BYTES = 65_536
MAX_SSE_BYTES = 67_108_864
MAX_SSE_LINE_BYTES = 2_097_152
MAX_SSE_EVENT_BYTES = 2_097_152

_SAFE_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_LINE_BREAK = re.compile(rb"[\r\n]")
_AUTH_CODES = frozenset({"invalid_api_key", "authentication_error", "permission_denied"})
_RATE_CODES = frozenset({"rate_limit_exceeded", "rate_limit_error"})


def require_standard_model(model: str, expected: str, stage: Stage) -> str:
    """Accept only the one Standard model id an adapter is written for (INV-4)."""
    if model != expected or model not in STANDARD_MODELS or model.endswith("-contributor"):
        raise AdLoomError("E_INPUT_INVALID", stage, "Only the Standard model id is allowed")
    return model


def build_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Create the only client configuration the live adapters are meant to use."""
    return httpx.Client(
        base_url=BASE_URL,
        timeout=TIMEOUT,
        trust_env=False,
        follow_redirects=False,
        transport=transport,
    )


def _safe_token(value: object) -> str | None:
    return value if isinstance(value, str) and _SAFE_TOKEN.fullmatch(value) else None


def provider_error_tokens(body: object) -> tuple[str | None, str | None]:
    """Return only enumerated ``error.type``/``error.code`` values, never the message."""
    error = body.get("error") if isinstance(body, Mapping) else None
    if not isinstance(error, Mapping):
        return None, None
    return _safe_token(error.get("type")), _safe_token(error.get("code"))


def status_error(
    status: int, body: object, stage: Stage, operation: str
) -> AdLoomError:
    kind, code = provider_error_tokens(body)
    detail = f"{operation} returned HTTP {status}"
    if kind or code:
        detail += f" ({kind or '-'}/{code or '-'})"
    error_code: ErrorCode
    retryable = False
    if status in (401, 403):
        error_code = "E_API_AUTH"
    elif status == 429:
        error_code, retryable = "E_API_RATE", True
    elif status == 413 or code == "payload_too_large":
        error_code = "E_RESOURCE_LIMIT"
    elif code == "content_policy_violation":
        error_code = "E_API_REFUSED"
    else:
        error_code = "E_API_REMOTE"
        retryable = status >= 500
    return AdLoomError(error_code, stage, detail, retryable)


def event_error(event: object, stage: Stage, operation: str) -> AdLoomError:
    """Classify a terminal ``response.failed`` or ``error`` stream event."""
    error: object = None
    if isinstance(event, Mapping):
        response = event.get("response")
        error = response.get("error") if isinstance(response, Mapping) else event.get("error")
    kind, code = provider_error_tokens({"error": error})
    detail = f"{operation} stream reported failure ({kind or '-'}/{code or '-'})"
    if code in _AUTH_CODES or kind == "authentication_error":
        return AdLoomError("E_API_AUTH", stage, detail)
    if code in _RATE_CODES or kind == "rate_limit_error":
        return AdLoomError("E_API_RATE", stage, detail, True)
    return AdLoomError("E_API_REMOTE", stage, detail)


def transport_error(error: httpx.HTTPError, stage: Stage, operation: str) -> AdLoomError:
    # Nothing reached the server on connect failures, so only those are safe to resend.
    retryable = isinstance(error, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout)
    return AdLoomError(
        "E_API_NETWORK", stage, f"{operation} failed: {type(error).__name__}", retryable
    )


def read_limited(response: httpx.Response, limit: int, stage: Stage) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > limit:
        raise AdLoomError("E_RESOURCE_LIMIT", stage, "Provider response exceeds the byte limit")
    body = bytearray()
    for chunk in response.iter_bytes():
        body += chunk
        if len(body) > limit:
            raise AdLoomError("E_RESOURCE_LIMIT", stage, "Provider response exceeds the byte limit")
    return bytes(body)


def parse_json_object(raw: bytes, stage: Stage, operation: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        raise AdLoomError("E_API_SCHEMA", stage, f"{operation} returned malformed JSON") from None
    if not isinstance(value, dict):
        raise AdLoomError("E_API_SCHEMA", stage, f"{operation} returned a non-object body")
    return value


class LimitedSyncStream(httpx.SyncByteStream):
    """Bound total bytes and physical line length before any SSE decoding happens."""

    def __init__(
        self, inner: httpx.SyncByteStream, max_total: int, max_line: int, stage: Stage
    ) -> None:
        self._inner = inner
        self._max_total = max_total
        self._max_line = max_line
        self._stage: Stage = stage

    def _limit(self) -> NoReturn:
        raise AdLoomError("E_RESOURCE_LIMIT", self._stage, "Provider stream exceeds the byte limit")

    def __iter__(self) -> Iterator[bytes]:
        total = 0
        line = 0
        for chunk in self._inner:
            total += len(chunk)
            if total > self._max_total:
                self._limit()
            parts = _LINE_BREAK.split(chunk)
            if len(parts) == 1:
                line += len(chunk)
            else:
                line += len(parts[0])
                if line > self._max_line or any(len(p) > self._max_line for p in parts[1:-1]):
                    self._limit()
                line = len(parts[-1])
            if line > self._max_line:
                self._limit()
            yield chunk

    def close(self) -> None:
        self._inner.close()


@dataclass
class ModelApi:
    """Authenticated access to fixed Model API paths with uniform error mapping."""

    api_key: str = field(repr=False)
    client: httpx.Client = field(default_factory=build_client, repr=False)
    uploads: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.api_key or not self.api_key.strip():
            raise AdLoomError("E_API_AUTH", "input", "Model API key is missing")

    def _headers(self, accept: str = "application/json") -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": accept}

    @staticmethod
    def url(path: str) -> str:
        if not path.startswith("/") or "//" in path or ".." in path:
            raise ValueError("Model API paths must be fixed absolute paths")
        return BASE_URL + path

    @contextmanager
    def _open(
        self, method: str, path: str, stage: Stage, operation: str, **kwargs: Any
    ) -> Iterator[httpx.Response]:
        try:
            with self.client.stream(method, self.url(path), **kwargs) as response:
                if response.is_redirect:
                    raise AdLoomError(
                        "E_API_REMOTE", stage, f"{operation} returned an unexpected redirect"
                    )
                if not response.is_success:
                    raw = read_limited(response, MAX_ERROR_BYTES, stage)
                    try:
                        body: object = json.loads(raw)
                    except ValueError:
                        body = None
                    raise status_error(response.status_code, body, stage, operation)
                yield response
        except httpx.HTTPError as error:
            raise transport_error(error, stage, operation) from None

    def request_json(
        self,
        method: str,
        path: str,
        stage: Stage,
        operation: str,
        *,
        limit: int = MAX_JSON_BYTES,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        with self._open(method, path, stage, operation, headers=headers, **kwargs) as response:
            raw = read_limited(response, limit, stage)
        return parse_json_object(raw, stage, operation)

    def post_json(
        self, path: str, payload: Mapping[str, object], stage: Stage, operation: str, **kw: Any
    ) -> dict[str, Any]:
        return self.request_json("POST", path, stage, operation, json=payload, **kw)

    def upload_file(self, path: Path, mime: str, stage: Stage) -> str:
        """Upload once per content digest and return the remote ``file-`` id.

        The id is kept in ``uploads`` so the caller can delete it later; Files
        never expire on the provider side.
        """
        size = path.stat().st_size
        if size > MAX_UPLOAD_BYTES:
            raise AdLoomError("E_RESOURCE_LIMIT", stage, "File exceeds the Files API upload limit")
        digest = file_hash(path)
        if digest in self.uploads:
            return self.uploads[digest]
        suffix = path.suffix.lower() or ".bin"
        with path.open("rb") as stream:
            body = self.request_json(
                "POST",
                "/files",
                stage,
                "File upload",
                data={"purpose": "user_data"},
                files={"file": (f"upload{suffix}", stream, mime)},
            )
        file_id = body.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise AdLoomError("E_API_SCHEMA", stage, "File upload response has no id")
        self.uploads[digest] = file_id
        return file_id

    def delete_file(self, file_id: str, stage: Stage) -> None:
        if not file_id or "/" in file_id:
            raise AdLoomError("E_INPUT_INVALID", stage, "Invalid remote file id")
        self.request_json("DELETE", f"/files/{file_id}", stage, "File delete")
        for digest, known in list(self.uploads.items()):
            if known == file_id:
                del self.uploads[digest]

    def delete_uploads(self, stage: Stage) -> tuple[str, ...]:
        """Try to delete every tracked upload; return the ids that are still remote."""
        failed: list[str] = []
        for file_id in tuple(self.uploads.values()):
            try:
                self.delete_file(file_id, stage)
            except AdLoomError:
                failed.append(file_id)
        return tuple(failed)

    @contextmanager
    def stream_events(
        self, path: str, payload: Mapping[str, object], stage: Stage, operation: str
    ) -> Iterator[Iterator[dict[str, Any]]]:
        """POST with ``stream=true`` and yield decoded SSE ``data`` objects in order."""
        headers = {
            **self._headers("text/event-stream"),
            "Accept-Encoding": "identity",
            "Cache-Control": "no-store",
        }
        with self._open("POST", path, stage, operation, headers=headers, json=payload) as response:
            content_type = response.headers.get("content-type", "").partition(";")[0].strip()
            if content_type != "text/event-stream":
                raise AdLoomError("E_API_SCHEMA", stage, f"{operation} did not return an SSE stream")
            encoding = response.headers.get("content-encoding", "identity").strip().lower()
            if encoding not in ("", "identity"):
                raise AdLoomError("E_API_SCHEMA", stage, f"{operation} stream is compressed")
            inner = response.stream
            if not isinstance(inner, httpx.SyncByteStream):
                raise TypeError("A synchronous HTTP client is required")
            response.stream = LimitedSyncStream(inner, MAX_SSE_BYTES, MAX_SSE_LINE_BYTES, stage)
            yield self._decode_events(EventSource(response), stage, operation)

    @staticmethod
    def _decode_events(
        source: EventSource, stage: Stage, operation: str
    ) -> Iterator[dict[str, Any]]:
        try:
            for sse in source.iter_sse():
                if sse.data == "[DONE]":
                    return
                if not sse.data:
                    continue
                if len(sse.data.encode()) > MAX_SSE_EVENT_BYTES:
                    raise AdLoomError("E_RESOURCE_LIMIT", stage, "Provider event exceeds the limit")
                yield parse_json_object(sse.data.encode(), stage, f"{operation} event")
        except httpx.HTTPError as error:
            raise transport_error(error, stage, operation) from None
