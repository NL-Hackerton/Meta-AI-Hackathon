"""LiveMarketing against httpx.MockTransport only; no request leaves the process."""

import base64
import email.parser
import email.policy
import json
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from adloom.adapters.base import PublishNotSent
from adloom.adapters.marketing import LiveMarketing
from adloom.config import AdLoomError
from adloom.jobs import file_hash

TOKEN = "test-token-not-a-secret"
ACCOUNT = "act_1234567890"
PAGE = "998877"
VERSION = "v26.0"
BASE = f"https://graph.facebook.com/{VERSION}"
KEY = "job1.r000001.campaign"

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, routes: dict[tuple[str, str], Handler] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        assert request.url.host == "graph.facebook.com"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert TOKEN not in str(request.url)
        assert TOKEN.encode() not in request.content
        handler = self.routes.get((request.method, request.url.path))
        assert handler is not None, f"unexpected {request.method} {request.url.path}"
        return handler(request)


def ok(body: dict[str, object]) -> Handler:
    return lambda _request: httpx.Response(200, json=body)


def graph_error(status: int, code: int, subcode: int | None = None) -> Handler:
    error: dict[str, object] = {
        "message": f"leaky message containing {TOKEN}",
        "type": "OAuthException",
        "code": code,
        "fbtrace_id": "Abc123",
    }
    if subcode is not None:
        error["error_subcode"] = subcode
    return lambda _request: httpx.Response(status, json={"error": error})


def adapter(
    recorder: Recorder, job_dir: Path, sleeps: list[float] | None = None, max_polls: int = 5
) -> LiveMarketing:
    log = sleeps if sleeps is not None else []
    return LiveMarketing(
        access_token=TOKEN,
        account_id=ACCOUNT,
        page_id=PAGE,
        graph_version=VERSION,
        job_dir=job_dir,
        client=httpx.Client(transport=httpx.MockTransport(recorder)),
        poll_interval=2.0,
        max_polls=max_polls,
        sleep=log.append,
    )


def form(request: httpx.Request) -> dict[str, str]:
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    parsed = parse_qs(request.content.decode(), keep_blank_values=True, strict_parsing=True)
    assert all(len(values) == 1 for values in parsed.values())
    return {name: values[0] for name, values in parsed.items()}


def multipart(request: httpx.Request) -> dict[str, tuple[str | None, bytes]]:
    head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(head + request.content)
    parts: dict[str, tuple[str | None, bytes]] = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        payload = part.get_payload(decode=True)
        assert isinstance(name, str) and isinstance(payload, bytes)
        parts[name] = (part.get_filename(), payload)
    return parts


CAMPAIGN = {
    "name": "job1",
    "objective": "OUTCOME_TRAFFIC",
    "status": "PAUSED",
    "special_ad_categories": [],
}
ADSET = {
    "campaign_id": "111",
    "daily_budget": 10000,
    "status": "PAUSED",
    "optimization_goal": "LINK_CLICKS",
    "billing_event": "IMPRESSIONS",
    "targeting": {"geo_locations": {"countries": ["KR"]}},
}
AD = {"adset_id": "222", "creative_id": "333", "status": "PAUSED"}
CREATIVE = {
    "page_id": PAGE,
    "video_id": "444",
    "image_hash": "abcdef0123",
    "primary_text": "본문 텍스트",
    "headline": "헤드라인",
    "cta": "LEARN_MORE",
    "destination_url": "https://example.com/landing",
}


def test_campaign_request_shape(tmp_path: Path) -> None:
    recorder = Recorder({("POST", f"/{VERSION}/{ACCOUNT}/campaigns"): ok({"id": "111"})})
    assert adapter(recorder, tmp_path).create("campaign", dict(CAMPAIGN), KEY) == "111"
    (request,) = recorder.requests
    assert str(request.url) == f"{BASE}/{ACCOUNT}/campaigns"
    assert form(request) == {
        "name": "job1",
        "objective": "OUTCOME_TRAFFIC",
        "status": "PAUSED",
        "special_ad_categories": "[]",
        "is_adset_budget_sharing_enabled": "false",
    }


def test_adset_request_shape_keeps_krw_whole_units(tmp_path: Path) -> None:
    recorder = Recorder({("POST", f"/{VERSION}/{ACCOUNT}/adsets"): ok({"id": "222"})})
    key = "job1.r000001.adset"
    assert adapter(recorder, tmp_path).create("adset", dict(ADSET), key) == "222"
    body = form(recorder.requests[0])
    assert json.loads(body.pop("targeting")) == {"geo_locations": {"countries": ["KR"]}}
    assert body == {
        "name": key,
        "campaign_id": "111",
        "daily_budget": "10000",
        "status": "PAUSED",
        "optimization_goal": "LINK_CLICKS",
        "billing_event": "IMPRESSIONS",
        "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
        "destination_type": "WEBSITE",
    }


@pytest.mark.parametrize("budget", [0, -1, 1.5, "10000", True])
def test_adset_rejects_invalid_budget_before_request(tmp_path: Path, budget: object) -> None:
    recorder = Recorder()
    with pytest.raises(PublishNotSent) as caught:
        adapter(recorder, tmp_path).create("adset", {**ADSET, "daily_budget": budget}, KEY)
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert recorder.requests == []


def test_ad_request_shape(tmp_path: Path) -> None:
    recorder = Recorder({("POST", f"/{VERSION}/{ACCOUNT}/ads"): ok({"id": "555"})})
    key = "job1.r000001.ad.h1"
    assert adapter(recorder, tmp_path).create("ad", dict(AD), key) == "555"
    body = form(recorder.requests[0])
    assert json.loads(body.pop("creative")) == {"creative_id": "333"}
    assert body == {"name": key, "adset_id": "222", "status": "PAUSED"}


def test_creative_request_shape(tmp_path: Path) -> None:
    recorder = Recorder({("POST", f"/{VERSION}/{ACCOUNT}/adcreatives"): ok({"id": "333"})})
    key = "job1.r000001.creative.h1"
    assert adapter(recorder, tmp_path).create("creative", dict(CREATIVE), key) == "333"
    body = form(recorder.requests[0])
    spec = json.loads(body.pop("object_story_spec"))
    assert body == {"name": key}
    assert spec == {
        "page_id": PAGE,
        "video_data": {
            "video_id": "444",
            "image_hash": "abcdef0123",
            "message": "본문 텍스트",
            "title": "헤드라인",
            "call_to_action": {
                "type": "LEARN_MORE",
                "value": {"link": "https://example.com/landing"},
            },
        },
    }


@pytest.mark.parametrize(
    "change",
    [
        {"destination_url": None},
        {"destination_url": "ftp://example.com"},
        {"page_id": "other-page"},
        {"cta": "SHOP_NOW"},
        {"video_id": ""},
        {"image_hash": None},
    ],
)
def test_creative_refuses_invalid_input_before_request(
    tmp_path: Path, change: dict[str, object]
) -> None:
    recorder = Recorder()
    with pytest.raises(PublishNotSent) as caught:
        adapter(recorder, tmp_path).create("creative", {**CREATIVE, **change}, KEY)
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert recorder.requests == []


@pytest.mark.parametrize("resource", ["campaign", "adset", "ad"])
@pytest.mark.parametrize("status", ["ACTIVE", None, "paused", "ARCHIVED"])
def test_non_paused_status_is_refused_before_request(
    tmp_path: Path, resource: str, status: object
) -> None:
    payload = {"campaign": CAMPAIGN, "adset": ADSET, "ad": AD}[resource]
    recorder = Recorder()
    with pytest.raises(PublishNotSent) as caught:
        adapter(recorder, tmp_path).create(resource, {**payload, "status": status}, KEY)
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert recorder.requests == []


def test_active_anywhere_in_payload_is_refused(tmp_path: Path) -> None:
    recorder = Recorder()
    nested = {**ADSET, "targeting": {"geo_locations": {"countries": ["KR"]}, "x": ["ACTIVE"]}}
    with pytest.raises(PublishNotSent):
        adapter(recorder, tmp_path).create("adset", nested, KEY)
    with pytest.raises(PublishNotSent):
        adapter(recorder, tmp_path).create(
            "campaign", {**CAMPAIGN, "configured_status": "ACTIVE"}, KEY
        )
    assert recorder.requests == []


def test_unknown_resource_is_refused(tmp_path: Path) -> None:
    recorder = Recorder()
    with pytest.raises(PublishNotSent):
        adapter(recorder, tmp_path).create("page", {"status": "PAUSED"}, KEY)
    assert recorder.requests == []


@pytest.mark.parametrize("account", ["1234", "act_", "act_12a", "act_1/../x", " act_1"])
def test_account_id_must_be_act_digits(tmp_path: Path, account: str) -> None:
    with pytest.raises(AdLoomError) as caught:
        LiveMarketing(TOKEN, account, PAGE, VERSION, tmp_path, client=httpx.Client())
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("version", ["26.0", "v26", "latest", "v26.0/..", ""])
def test_graph_version_must_be_pinned(tmp_path: Path, version: str) -> None:
    with pytest.raises(AdLoomError):
        LiveMarketing(TOKEN, ACCOUNT, PAGE, version, tmp_path, client=httpx.Client())


def test_token_is_not_in_repr(tmp_path: Path) -> None:
    live = adapter(Recorder(), tmp_path)
    assert TOKEN not in repr(live)
    assert TOKEN not in repr(vars(live))


def write_asset(job_dir: Path, relative: str, data: bytes) -> dict[str, object]:
    path = job_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"sha256": file_hash(path), "path": relative}


PNG = b"\x89PNG\r\n\x1a\nnot-a-real-png-but-bytes"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def test_image_upload_returns_hash(tmp_path: Path) -> None:
    payload = write_asset(tmp_path, "enrich/thumb_9x16.png", PNG)
    recorder = Recorder(
        {
            ("POST", f"/{VERSION}/{ACCOUNT}/adimages"): ok(
                {"images": {"bytes": {"hash": "abcdef0123", "url": "https://x"}}}
            )
        }
    )
    assert adapter(recorder, tmp_path).create("image", payload, KEY) == "abcdef0123"
    body = form(recorder.requests[0])
    assert body == {"bytes": base64.b64encode(PNG).decode()}


def test_video_upload_polls_until_ready(tmp_path: Path) -> None:
    payload = write_asset(tmp_path, "render/h1_9x16.mp4", MP4)
    statuses = iter(["processing", "processing", "ready"])

    def status(request: httpx.Request) -> httpx.Response:
        assert request.url.params["fields"] == "status"
        return httpx.Response(200, json={"id": "444", "status": {"video_status": next(statuses)}})

    recorder = Recorder(
        {
            ("POST", f"/{VERSION}/{ACCOUNT}/advideos"): ok({"id": "444"}),
            ("GET", f"/{VERSION}/444"): status,
        }
    )
    sleeps: list[float] = []
    key = "job1.r000001.video.h1"
    assert adapter(recorder, tmp_path, sleeps).create("video", payload, key) == "444"
    upload, *polls = recorder.requests
    assert len(polls) == 3 and sleeps == [2.0, 2.0]
    parts = multipart(upload)
    assert parts["source"] == ("h1_9x16.mp4", MP4)
    assert parts["name"] == (None, key.encode())
    assert set(parts) == {"source", "name"}


def test_video_poll_is_bounded(tmp_path: Path) -> None:
    payload = write_asset(tmp_path, "render/h1_9x16.mp4", MP4)
    recorder = Recorder(
        {
            ("POST", f"/{VERSION}/{ACCOUNT}/advideos"): ok({"id": "444"}),
            ("GET", f"/{VERSION}/444"): ok({"status": {"video_status": "processing"}}),
        }
    )
    sleeps: list[float] = []
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path, sleeps, max_polls=4).create("video", payload, KEY)
    assert not isinstance(caught.value, PublishNotSent)
    assert caught.value.error.code == "E_API_INCOMPLETE"
    assert "444" in caught.value.error.detail
    assert len(recorder.requests) == 1 + 4 and len(sleeps) == 3


@pytest.mark.parametrize(
    "handler",
    [ok({"status": {"video_status": "error"}}), graph_error(400, 190), ok({"status": "odd"})],
)
def test_video_failure_after_upload_is_unknown(tmp_path: Path, handler: Handler) -> None:
    payload = write_asset(tmp_path, "render/h1_9x16.mp4", MP4)
    recorder = Recorder(
        {
            ("POST", f"/{VERSION}/{ACCOUNT}/advideos"): ok({"id": "444"}),
            ("GET", f"/{VERSION}/444"): handler,
        }
    )
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).create("video", payload, KEY)
    assert not isinstance(caught.value, PublishNotSent)
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize("resource", ["image", "video"])
def test_hash_mismatch_is_refused_before_request(tmp_path: Path, resource: str) -> None:
    payload = write_asset(tmp_path, "asset.bin", b"original")
    (tmp_path / "asset.bin").write_bytes(b"changed")
    recorder = Recorder()
    with pytest.raises(PublishNotSent) as caught:
        adapter(recorder, tmp_path).create(resource, payload, KEY)
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert recorder.requests == []


@pytest.mark.parametrize("path", ["../outside.png", "/etc/passwd", "missing.png", "", "dir"])
def test_asset_path_must_stay_inside_job(tmp_path: Path, path: str) -> None:
    job = tmp_path / "job"
    (job / "dir").mkdir(parents=True)
    (tmp_path / "outside.png").write_bytes(PNG)
    recorder = Recorder()
    with pytest.raises(PublishNotSent):
        adapter(recorder, job).create("image", {"sha256": "0" * 64, "path": path}, KEY)
    assert recorder.requests == []


def test_symlink_escape_is_refused(tmp_path: Path) -> None:
    job = tmp_path / "job"
    job.mkdir()
    (tmp_path / "outside.png").write_bytes(PNG)
    (job / "link.png").symlink_to(tmp_path / "outside.png")
    recorder = Recorder()
    with pytest.raises(PublishNotSent):
        adapter(recorder, job).create(
            "image", {"sha256": file_hash(tmp_path / "outside.png"), "path": "link.png"}, KEY
        )
    assert recorder.requests == []


@pytest.mark.parametrize(
    ("status", "code", "subcode", "expected", "not_sent"),
    [
        (400, 190, None, "E_API_AUTH", True),
        (401, 102, None, "E_API_AUTH", True),
        (403, 10, None, "E_API_AUTH", True),
        (403, 200, None, "E_API_AUTH", True),
        (403, 294, None, "E_API_AUTH", True),
        (400, 4, None, "E_API_RATE", True),
        (400, 17, 2446079, "E_API_RATE", True),
        (400, 32, None, "E_API_RATE", True),
        (400, 613, 1487742, "E_API_RATE", True),
        (400, 80004, None, "E_API_RATE", True),
        (400, 100, 1487901, "E_API_REMOTE", False),
        (500, 1, None, "E_API_REMOTE", False),
        (500, 2, None, "E_API_REMOTE", False),
    ],
)
def test_graph_error_mapping(
    tmp_path: Path,
    status: int,
    code: int,
    subcode: int | None,
    expected: str,
    not_sent: bool,
) -> None:
    recorder = Recorder(
        {("POST", f"/{VERSION}/{ACCOUNT}/campaigns"): graph_error(status, code, subcode)}
    )
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).create("campaign", dict(CAMPAIGN), KEY)
    assert caught.value.error.code == expected
    assert isinstance(caught.value, PublishNotSent) is not_sent
    assert len(recorder.requests) == 1  # never retried
    detail = caught.value.error.detail
    assert f"code {code}" in detail
    assert "leaky" not in detail and TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, text="<html>bad gateway</html>"),
        httpx.Response(400, json={"error": "not-an-object"}),
        httpx.Response(400, json={"error": {"code": True}}),
    ],
)
def test_unparseable_error_is_unknown(tmp_path: Path, response: httpx.Response) -> None:
    recorder = Recorder({("POST", f"/{VERSION}/{ACCOUNT}/campaigns"): lambda _r: response})
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).create("campaign", dict(CAMPAIGN), KEY)
    assert not isinstance(caught.value, PublishNotSent)
    assert caught.value.error.code == "E_API_REMOTE"


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[]", b'{"success": true}', b'{"id": ""}', b'{"id": "1/../2"}'],
)
def test_malformed_success_is_partial(tmp_path: Path, body: bytes) -> None:
    recorder = Recorder(
        {("POST", f"/{VERSION}/{ACCOUNT}/campaigns"): lambda _r: httpx.Response(200, content=body)}
    )
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).create("campaign", dict(CAMPAIGN), KEY)
    assert not isinstance(caught.value, PublishNotSent)
    assert caught.value.error.code == "E_PUBLISH_PARTIAL"


@pytest.mark.parametrize(
    ("error", "not_sent", "expected"),
    [
        (httpx.ConnectError("refused"), True, "E_API_NETWORK"),
        (httpx.ConnectTimeout("slow"), True, "E_API_NETWORK"),
        (httpx.ReadTimeout("slow"), False, "E_PUBLISH_PARTIAL"),
        (httpx.WriteTimeout("slow"), False, "E_PUBLISH_PARTIAL"),
        (httpx.ReadError("reset"), False, "E_PUBLISH_PARTIAL"),
        (httpx.RemoteProtocolError("eof"), False, "E_PUBLISH_PARTIAL"),
    ],
)
def test_transport_errors(
    tmp_path: Path, error: httpx.HTTPError, not_sent: bool, expected: str
) -> None:
    calls: list[httpx.Request] = []

    def boom(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise error

    live = LiveMarketing(
        TOKEN,
        ACCOUNT,
        PAGE,
        VERSION,
        tmp_path,
        client=httpx.Client(transport=httpx.MockTransport(boom)),
    )
    with pytest.raises(AdLoomError) as caught:
        live.create("campaign", dict(CAMPAIGN), KEY)
    assert isinstance(caught.value, PublishNotSent) is not_sent
    assert caught.value.error.code == expected
    assert len(calls) == 1


def test_read_gets_fields(tmp_path: Path) -> None:
    def node(request: httpx.Request) -> httpx.Response:
        assert request.url.params["fields"] == "id,status,effective_status"
        return httpx.Response(200, json={"id": "111", "status": "PAUSED"})

    recorder = Recorder({("GET", f"/{VERSION}/111"): node})
    live = adapter(recorder, tmp_path)
    assert live.read("111", ("id", "status", "effective_status")) == {
        "id": "111",
        "status": "PAUSED",
    }
    assert [r.method for r in recorder.requests] == ["GET"]


@pytest.mark.parametrize(
    ("resource_id", "fields"),
    [("1/../me", ("id",)), ("", ("id",)), ("111", ()), ("111", ("id&x=1",))],
)
def test_read_validates_input(tmp_path: Path, resource_id: str, fields: tuple[str, ...]) -> None:
    recorder = Recorder()
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).read(resource_id, fields)
    assert caught.value.error.code == "E_INPUT_INVALID"
    assert recorder.requests == []


def test_read_maps_errors(tmp_path: Path) -> None:
    recorder = Recorder({("GET", f"/{VERSION}/111"): graph_error(400, 190)})
    with pytest.raises(AdLoomError) as caught:
        adapter(recorder, tmp_path).read("111", ("status",))
    assert caught.value.error.code == "E_API_AUTH"
