"""Live Marketing API publisher (Graph API ``act_{id}/...`` create edges).

Nothing here reads the environment or decides whether live execution is allowed; that gate
stays in ``adloom.config``. Every create is sent at most once: a failure is raised as
``PublishNotSent`` only when no request bytes can have changed anything at Meta (local
validation, connect failures, and auth/rate rejections), otherwise as a plain ``AdLoomError``
that the publish journal records as UNKNOWN and never resends. Field choices and their
sources are in ``docs/api_notes/marketing.md``.
"""

import base64
import hashlib
import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NoReturn

import httpx

from adloom.adapters.base import PublishNotSent
from adloom.config import ALLOWED_CTAS, AdLoomError
from adloom.schemas import ErrorCode

GRAPH_URL = "https://graph.facebook.com"
TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=300.0, pool=10.0)
# Creative docs: images "Not to exceed 8MB in size".
MAX_IMAGE_BYTES = 8_000_000
# Self-imposed cap for the one-request (non-chunked) ``source`` upload; rendered ads are a few MB.
MAX_VIDEO_BYTES = 104_857_600
MAX_RESPONSE_BYTES = 1_048_576
POLL_INTERVAL = 5.0
MAX_POLLS = 60

_ACCOUNT = re.compile(r"act_[0-9]{1,32}")
_VERSION = re.compile(r"v[0-9]{1,3}\.[0-9]{1,2}")
_NODE_ID = re.compile(r"[0-9]{1,32}")
_IMAGE_HASH = re.compile(r"[A-Za-z0-9_-]{1,128}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,200}")
_FIELD = re.compile(r"[a-z_][a-z0-9_]{0,63}")
_TOKEN = re.compile(r"[A-Z_]{1,64}")
_ERROR_TYPE = re.compile(r"[A-Za-z_]{1,64}")
# Graph error codes: 190/102/104 invalid session or token, 10 and 200-299 permission.
_AUTH_CODES = frozenset({10, 102, 104, 190})
# 4/17/32/613 app, user, page and ad-account call limits; 80000-80014 business use case limits.
_RATE_CODES = frozenset({4, 17, 32, 613})

_ALLOWED_KEYS: dict[str, frozenset[str]] = {
    "campaign": frozenset({"name", "objective", "status", "special_ad_categories"}),
    "adset": frozenset(
        {
            "name",
            "campaign_id",
            "daily_budget",
            "status",
            "optimization_goal",
            "billing_event",
            "targeting",
            "bid_strategy",
            "destination_type",
        }
    ),
    "ad": frozenset({"name", "adset_id", "creative_id", "status"}),
    "creative": frozenset(
        {
            "name",
            "page_id",
            "video_id",
            "image_hash",
            "primary_text",
            "headline",
            "cta",
            "destination_url",
        }
    ),
    "image": frozenset({"sha256", "path"}),
    "video": frozenset({"sha256", "path"}),
}


class _Secret:
    """Keeps the access token out of ``repr``/``vars`` output."""

    __slots__ = ("value",)

    def __init__(self, value: str) -> None:
        self.value = value

    def __repr__(self) -> str:
        return "_Secret('***')"


def _refuse(detail: str, code: ErrorCode = "E_INPUT_INVALID") -> NoReturn:
    raise PublishNotSent(code, "publish", detail)


def _contains_active(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().upper() == "ACTIVE"
    if isinstance(value, Mapping):
        return any(_contains_active(k) or _contains_active(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_contains_active(item) for item in value)
    return False


def _encode(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        _refuse(f"Field {key} must be a non-empty string")
    return value


def _node_id(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not _NODE_ID.fullmatch(value):
        _refuse(f"Field {key} must be a numeric Graph id")
    return value


def _enum(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not _TOKEN.fullmatch(value):
        _refuse(f"Field {key} must be an upper-case enum value")
    return value


def _error_tokens(raw: bytes) -> tuple[int | None, int | None, str | None]:
    """Return only Graph ``error.code``/``error_subcode``/``type``, never the message."""
    try:
        body = json.loads(raw)
    except (UnicodeDecodeError, ValueError):
        return None, None, None
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return None, None, None

    def number(value: object) -> int | None:
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    kind = error.get("type")
    return (
        number(error.get("code")),
        number(error.get("error_subcode")),
        kind if isinstance(kind, str) and _ERROR_TYPE.fullmatch(kind) else None,
    )


class LiveMarketing:
    """MarketingPublisher that creates PAUSED Marketing API objects in one ad account."""

    def __init__(
        self,
        access_token: str,
        account_id: str,
        page_id: str,
        graph_version: str,
        job_dir: Path,
        client: httpx.Client | None = None,
        *,
        poll_interval: float = POLL_INTERVAL,
        max_polls: int = MAX_POLLS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(account_id, str) or not _ACCOUNT.fullmatch(account_id):
            raise AdLoomError(
                "E_INPUT_INVALID", "publish", "Ad account id must look like act_<digits>"
            )
        if not isinstance(page_id, str) or not _NODE_ID.fullmatch(page_id):
            raise AdLoomError("E_INPUT_INVALID", "publish", "Page id must be numeric")
        if not isinstance(graph_version, str) or not _VERSION.fullmatch(graph_version):
            raise AdLoomError(
                "E_INPUT_INVALID", "publish", "Graph version must be pinned, e.g. v26.0"
            )
        if not access_token or any(c.isspace() for c in access_token):
            raise AdLoomError("E_API_AUTH", "publish", "Marketing access token is missing")
        if max_polls < 1 or poll_interval < 0:
            raise AdLoomError("E_INPUT_INVALID", "publish", "Invalid video polling bounds")
        self._token = _Secret(access_token)
        self.account_id = account_id
        self.page_id = page_id
        self.graph_version = graph_version
        self.job_dir = job_dir
        self._client = client or httpx.Client(
            timeout=TIMEOUT, trust_env=False, follow_redirects=False
        )
        self._poll_interval = poll_interval
        self._max_polls = max_polls
        self._sleep = sleep

    def __repr__(self) -> str:
        return (
            f"LiveMarketing(account_id={self.account_id!r}, graph_version={self.graph_version!r})"
        )

    # MarketingPublisher -------------------------------------------------------------------

    def create(self, resource: str, payload: dict[str, object], operation_key: str) -> str:
        allowed = _ALLOWED_KEYS.get(resource)
        if allowed is None:
            _refuse("Unknown publish resource")
        if not isinstance(operation_key, str) or not _KEY.fullmatch(operation_key):
            _refuse("Invalid operation key")
        if set(payload) - allowed:
            _refuse(f"Unexpected {resource} fields: {sorted(set(payload) - allowed)}")
        # INV-2: nothing this adapter sends may ever carry ACTIVE.
        if _contains_active(payload):
            _refuse("ACTIVE is never sent; publishing is PAUSED only")
        if resource in {"campaign", "adset", "ad"} and payload.get("status") != "PAUSED":
            _refuse("Campaigns, ad sets and ads must be created PAUSED")
        name = payload.get("name", operation_key)
        if not isinstance(name, str) or not name.strip():
            _refuse("Name must be a non-empty string")
        if resource == "campaign":
            return self._create_node("campaigns", self._campaign(payload, name), "Campaign create")
        if resource == "adset":
            return self._create_node("adsets", self._adset(payload, name), "Ad set create")
        if resource == "ad":
            return self._create_node("ads", self._ad(payload, name), "Ad create")
        if resource == "creative":
            return self._create_node(
                "adcreatives", self._creative(payload, name), "Creative create"
            )
        if resource == "image":
            return self._upload_image(payload)
        return self._upload_video(payload, name)

    def read(self, resource_id: str, fields: Sequence[str]) -> dict[str, Any]:
        """GET one node for reconcile; never mutates anything."""
        if not isinstance(resource_id, str) or not _NODE_ID.fullmatch(resource_id):
            raise AdLoomError("E_INPUT_INVALID", "publish", "Resource id must be numeric")
        if not fields or not all(isinstance(f, str) and _FIELD.fullmatch(f) for f in fields):
            raise AdLoomError("E_INPUT_INVALID", "publish", "Invalid field list")
        return self._request(
            "GET", resource_id, "Node read", create=False, params={"fields": ",".join(fields)}
        )

    def close(self) -> None:
        self._client.close()

    # Payload builders (all validation happens before any request) -------------------------

    def _campaign(self, payload: Mapping[str, object], name: str) -> dict[str, str]:
        categories = payload.get("special_ad_categories")
        if not isinstance(categories, list) or not all(
            isinstance(c, str) and _TOKEN.fullmatch(c) for c in categories
        ):
            _refuse("special_ad_categories must be a list of enum values")
        return {
            "name": name,
            "objective": _enum(payload, "objective"),
            "status": "PAUSED",
            "special_ad_categories": _encode(categories),
            # Budget lives on the ad set, so ad set budget sharing is explicitly off.
            "is_adset_budget_sharing_enabled": "false",
        }

    def _adset(self, payload: Mapping[str, object], name: str) -> dict[str, str]:
        budget = payload.get("daily_budget")
        # KRW has offset 1 in the currency table: the value is whole won, not minor units.
        if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0:
            _refuse("daily_budget must be a positive integer in account currency units")
        targeting = payload.get("targeting")
        if not isinstance(targeting, Mapping):
            _refuse("targeting must be an object")
        geo = targeting.get("geo_locations")
        if not isinstance(geo, Mapping) or not geo.get("countries"):
            _refuse("targeting.geo_locations.countries is required")
        return {
            "name": name,
            "campaign_id": _node_id(payload, "campaign_id"),
            "daily_budget": str(budget),
            "status": "PAUSED",
            "optimization_goal": _enum(payload, "optimization_goal"),
            "billing_event": _enum(payload, "billing_event"),
            "targeting": _encode(dict(targeting)),
            "bid_strategy": (
                _enum(payload, "bid_strategy")
                if "bid_strategy" in payload
                else "LOWEST_COST_WITHOUT_CAP"
            ),
            "destination_type": (
                _enum(payload, "destination_type") if "destination_type" in payload else "WEBSITE"
            ),
        }

    def _ad(self, payload: Mapping[str, object], name: str) -> dict[str, str]:
        return {
            "name": name,
            "adset_id": _node_id(payload, "adset_id"),
            "creative": _encode({"creative_id": _node_id(payload, "creative_id")}),
            "status": "PAUSED",
        }

    def _creative(self, payload: Mapping[str, object], name: str) -> dict[str, str]:
        if payload.get("page_id", self.page_id) != self.page_id:
            _refuse("Creative page_id does not match the configured Page")
        image_hash = payload.get("image_hash")
        if not isinstance(image_hash, str) or not _IMAGE_HASH.fullmatch(image_hash):
            _refuse("image_hash is required")
        cta = payload.get("cta")
        if cta not in ALLOWED_CTAS:
            _refuse("Call to action is not allowed")
        destination = payload.get("destination_url")
        # Traffic ads need a website link; a Page-only video CTA is not documented, so refuse.
        if not isinstance(destination, str):
            _refuse("destination_url is required for a link call to action")
        try:
            url = httpx.URL(destination)
        except (httpx.InvalidURL, TypeError):
            _refuse("destination_url is not a valid URL")
        if url.scheme not in {"http", "https"} or not url.host:
            _refuse("destination_url must be an http(s) URL")
        spec = {
            "page_id": self.page_id,
            "video_data": {
                "video_id": _node_id(payload, "video_id"),
                "image_hash": image_hash,
                "message": _text(payload, "primary_text"),
                "title": _text(payload, "headline"),
                "call_to_action": {"type": cta, "value": {"link": destination}},
            },
        }
        return {"name": name, "object_story_spec": _encode(spec)}

    def _asset(self, payload: Mapping[str, object], limit: int) -> tuple[str, bytes]:
        relative = payload.get("path")
        expected = payload.get("sha256")
        if not isinstance(expected, str) or not _SHA256.fullmatch(expected):
            _refuse("Asset sha256 is missing")
        if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
            _refuse("Asset path must be job-relative")
        root = self.job_dir.resolve()
        try:
            path = (root / relative).resolve(strict=True)
        except (OSError, RuntimeError):
            _refuse("Asset is missing")
        if not path.is_relative_to(root) or not path.is_file():
            _refuse("Asset path must point to a file inside the job")
        if path.stat().st_size > limit:
            _refuse("Asset exceeds the upload size limit", "E_RESOURCE_LIMIT")
        # Hash the exact bytes that will be sent, so a later file change cannot slip through.
        data = path.read_bytes()
        if len(data) > limit:
            _refuse("Asset exceeds the upload size limit", "E_RESOURCE_LIMIT")
        if hashlib.sha256(data).hexdigest() != expected:
            _refuse("Asset changed since approval")
        return path.name, data

    # Requests ----------------------------------------------------------------------------

    def _create_node(self, edge: str, form: dict[str, str], operation: str) -> str:
        body = self._request("POST", f"{self.account_id}/{edge}", operation, create=True, data=form)
        return self._created_id(body, operation)

    def _upload_image(self, payload: Mapping[str, object]) -> str:
        _, data = self._asset(payload, MAX_IMAGE_BYTES)
        operation = "Image upload"
        body = self._request(
            "POST",
            f"{self.account_id}/adimages",
            operation,
            create=True,
            data={"bytes": base64.b64encode(data).decode("ascii")},
        )
        images = body.get("images")
        hashes = (
            [v.get("hash") for v in images.values() if isinstance(v, Mapping)]
            if isinstance(images, Mapping)
            else []
        )
        if (
            len(hashes) != 1
            or not isinstance(hashes[0], str)
            or not _IMAGE_HASH.fullmatch(hashes[0])
        ):
            raise AdLoomError(
                "E_PUBLISH_PARTIAL", "publish", f"{operation} returned no image hash; do not resend"
            )
        return hashes[0]

    def _upload_video(self, payload: Mapping[str, object], name: str) -> str:
        filename, data = self._asset(payload, MAX_VIDEO_BYTES)
        operation = "Video upload"
        body = self._request(
            "POST",
            f"{self.account_id}/advideos",
            operation,
            create=True,
            data={"name": name},
            files={"source": (filename, data, "video/mp4")},
        )
        video_id = self._created_id(body, operation)
        self._wait_for_video(video_id)
        return video_id

    def _wait_for_video(self, video_id: str) -> None:
        """Bounded wait until the uploaded video can be used in a creative."""
        for attempt in range(self._max_polls):
            if attempt:
                self._sleep(self._poll_interval)
            body = self._request(
                "GET", video_id, "Video status", create=False, params={"fields": "status"}
            )
            status = body.get("status")
            state = status.get("video_status") if isinstance(status, Mapping) else None
            if state == "ready":
                return
            if state == "processing":
                continue
            if state in {"error", "expired"}:
                raise AdLoomError(
                    "E_API_REMOTE", "publish", f"Video {video_id} processing ended in {state}"
                )
            raise AdLoomError(
                "E_API_SCHEMA", "publish", f"Video {video_id} status response is malformed"
            )
        raise AdLoomError(
            "E_API_INCOMPLETE",
            "publish",
            f"Video {video_id} was uploaded but still processing after {self._max_polls} checks",
        )

    def _created_id(self, body: Mapping[str, object], operation: str) -> str:
        value = body.get("id", body.get("video_id"))
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if not isinstance(value, str) or not _NODE_ID.fullmatch(value):
            raise AdLoomError(
                "E_PUBLISH_PARTIAL", "publish", f"{operation} returned no id; do not resend"
            )
        return value

    def _request(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        create: bool,
        data: Mapping[str, str] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        params: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{GRAPH_URL}/{self.graph_version}/{path}"
        headers = {"Authorization": f"Bearer {self._token.value}", "Accept": "application/json"}
        try:
            with self._client.stream(
                method,
                url,
                data=data,
                files=files,
                params=params,
                headers=headers,
                timeout=TIMEOUT,
            ) as response:
                raw, too_large = self._read_capped(response)
                status = response.status_code
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            # No request bytes left this process, so nothing can exist remotely.
            detail = f"{operation} could not connect: {type(error).__name__}"
            if create:
                raise PublishNotSent("E_API_NETWORK", "publish", detail, True) from None
            raise AdLoomError("E_API_NETWORK", "publish", detail, True) from None
        except httpx.HTTPError as error:
            detail = f"{operation} failed after sending: {type(error).__name__}"
            if create:
                raise AdLoomError(
                    "E_PUBLISH_PARTIAL", "publish", detail + "; outcome unknown, do not resend"
                ) from None
            raise AdLoomError("E_API_NETWORK", "publish", detail, True) from None
        if not 200 <= status < 300:
            raise self._status_error(status, raw, operation, create)
        if too_large:
            if create:
                raise AdLoomError(
                    "E_PUBLISH_PARTIAL", "publish", f"{operation} response too large; do not resend"
                )
            raise AdLoomError("E_RESOURCE_LIMIT", "publish", f"{operation} response too large")
        try:
            body = json.loads(raw)
        except (UnicodeDecodeError, ValueError):
            body = None
        if not isinstance(body, dict):
            if create:
                raise AdLoomError(
                    "E_PUBLISH_PARTIAL",
                    "publish",
                    f"{operation} returned malformed JSON; do not resend",
                )
            raise AdLoomError("E_API_SCHEMA", "publish", f"{operation} returned malformed JSON")
        return body

    @staticmethod
    def _read_capped(response: httpx.Response) -> tuple[bytes, bool]:
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                return bytes(body[:MAX_RESPONSE_BYTES]), True
        return bytes(body), False

    @staticmethod
    def _status_error(status: int, raw: bytes, operation: str, create: bool) -> AdLoomError:
        code, subcode, kind = _error_tokens(raw)
        detail = (
            f"{operation} returned HTTP {status} "
            f"(code {code if code is not None else '-'}, "
            f"subcode {subcode if subcode is not None else '-'}, type {kind or '-'})"
        )
        error_code: ErrorCode
        rejected = False
        retryable = False
        if code is not None and (code in _AUTH_CODES or 200 <= code <= 299):
            error_code, rejected = "E_API_AUTH", True
        elif code is not None and (code in _RATE_CODES or 80000 <= code <= 80014):
            error_code, rejected, retryable = "E_API_RATE", True, True
        else:
            error_code = "E_API_REMOTE"
            retryable = status >= 500 and not create
        # Auth and throttling are rejected before the edge handler runs, so nothing was created.
        if create and rejected and 400 <= status < 500:
            return PublishNotSent(error_code, "publish", detail, retryable)
        if create:
            return AdLoomError(error_code, "publish", detail + "; outcome unknown, do not resend")
        return AdLoomError(error_code, "publish", detail, retryable)
