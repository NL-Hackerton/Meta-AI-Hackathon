"""Live Model API adapters against httpx.MockTransport only; no request leaves the process."""

import base64
import email.parser
import email.policy
import io
import json
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from PIL import Image

from adloom.adapters.base import get_adapters
from adloom.adapters.image import LiveImage
from adloom.adapters.model_api import BASE_URL, build_client
from adloom.adapters.sam import LiveTracking
from adloom.adapters.spark import LiveSpark, strict_schema
from adloom.adapters.voice import LiveVoice
from adloom.config import AdLoomError, load_config
from adloom.schemas import Understanding

KEY = "test-key-not-a-secret"
UNDERSTANDING = Path(
    "tests/fixtures/understanding/"
    "19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json"
).read_text()

# Frame 0 of the documented six-frame, 320x334 "button" clip (reading-segmentation and
# the meta-sam-parser README); the mask payloads are real lossless payloads.
OBJ0 = (
    "0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,60,~!!!!M!0c[0o91w?q1!pIH4pPRVp2B3'7`e.ioeAf6-k/#Xd8%dX9x(|>"
)
OBJ1 = (
    "1<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334|>"
    "<|mask;x=0;y=0;data=27,48,~!!!!J!0c[q=Pj_zs=*4C4(/./x#:/`S_GnD`=o3?X{emCgO$y@|>"
)

Handler = Callable[[httpx.Request], httpx.Response]


class Recorder:
    def __init__(self, routes: dict[tuple[str, str], Handler]) -> None:
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        assert request.url.host == "api.meta.ai"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        handler = self.routes.get((request.method, request.url.path))
        assert handler is not None, f"unexpected {request.method} {request.url.path}"
        return handler(request)

    def client(self) -> httpx.Client:
        return build_client(transport=httpx.MockTransport(self))

    def paths(self) -> list[str]:
        return [f"{r.method} {r.url.path}" for r in self.requests]


def uploaded(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "file-123", "object": "file", "status": "uploaded"})


def responses_body(text: str) -> dict[str, object]:
    return {
        "id": "resp_1",
        "object": "response",
        "status": "completed",
        "model": "muse-spark-1.3",
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": text, "annotations": []}],
            },
        ],
    }


def sse(events: list[dict[str, object]]) -> bytes:
    lines = []
    for event in events:
        lines.append(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n")
    return "".join(lines).encode()


def sam_events(frame_lines: list[str], *, terminal: str = "response.completed") -> bytes:
    lane = {"item_id": "msg_1", "output_index": 0, "content_index": 0}
    events: list[dict[str, object]] = [{"type": "response.created", "response": {"id": "r"}}]
    events += [{"type": "response.output_text.delta", **lane, "delta": f"{line}\n"} for line in frame_lines]
    text = "".join(f"{line}\n" for line in frame_lines)
    events.append(
        {"type": "response.content_part.done", **lane, "part": {"type": "output_text", "text": text}}
    )
    if terminal == "response.completed":
        events.append({"type": "response.completed", "response": {"status": "completed"}})
    elif terminal == "response.incomplete":
        events.append(
            {
                "type": "response.incomplete",
                "response": {"incomplete_details": {"reason": "max_output_tokens"}},
            }
        )
    return sse(events)


def event_stream(body: bytes) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=body)

    return handle


@pytest.fixture(scope="module")
def clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("clip") / "clip.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=320x334:r=30:d=0.2",
            "-pix_fmt", "yuv420p", "-c:v", "libx264", "-y", str(path),
        ],
        check=True,
    )
    return path


@pytest.fixture(scope="module")
def tone(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("tone") / "note.m4a"
    subprocess.run(
        [
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-ac", "2", "-ar", "44100", "-c:a", "aac", "-y", str(path),
        ],
        check=True,
    )
    return path


# --- shared boundary -----------------------------------------------------------------


def test_factory_still_returns_only_mocks(tmp_path):
    adapters = get_adapters(load_config({}), tmp_path)
    assert {type(a).__name__ for a in adapters.__dict__.values()} == {
        "MockSpark", "MockTracking", "MockImage", "MockVoice", "MockMarketing",
    }
    with pytest.raises(AdLoomError, match="E_API_AUTH"):
        load_config({"ADLOOM_LIVE": "1", "MODEL_API_KEY": KEY})


def test_client_is_pinned_to_model_api_without_env_or_redirects():
    client = build_client()
    assert str(client.base_url).rstrip("/") == BASE_URL
    assert client.trust_env is False
    assert client.follow_redirects is False
    assert client.timeout.connect == 10.0 and client.timeout.read == 120.0


@pytest.mark.parametrize(
    ("factory", "model"),
    [
        (lambda m, tmp: LiveSpark(KEY, model=m), "muse-spark-1.3-contributor"),
        (lambda m, tmp: LiveTracking(KEY, model=m), "sam-3.1-contributor"),
        (lambda m, tmp: LiveImage(KEY, output=tmp, model=m), "muse-image-1.0-contributor"),
        (lambda m, tmp: LiveVoice(KEY, job_dir=tmp, model=m), "muse-voice-transcribe-1.0-contributor"),
        (lambda m, tmp: LiveSpark(KEY, model=m), "sam-3.1"),
    ],
)
def test_only_the_standard_model_id_is_accepted(factory, model, tmp_path):
    with pytest.raises(AdLoomError, match="E_INPUT_INVALID"):
        factory(model, tmp_path)


def test_missing_key_is_an_auth_error():
    with pytest.raises(AdLoomError, match="E_API_AUTH"):
        LiveSpark("  ")


# --- Spark ---------------------------------------------------------------------------


def test_spark_uploads_once_and_requests_strict_structured_output(clip):
    recorder = Recorder(
        {
            ("POST", "/v1/files"): uploaded,
            ("POST", "/v1/responses"): lambda r: httpx.Response(200, json=responses_body(UNDERSTANDING)),
        }
    )
    spark = LiveSpark(KEY, recorder.client())
    first = spark.understand(clip, "수제 머그컵", "ko")
    assert Understanding.model_validate_json(first).sam_prompt == "gold square"
    spark.understand(clip, "수제 머그컵", "ko", feedback="hook_candidates: too many items")
    assert recorder.paths() == ["POST /v1/files", "POST /v1/responses", "POST /v1/responses"]

    upload = recorder.requests[0]
    assert upload.headers["content-type"].startswith("multipart/form-data")
    assert b'name="purpose"\r\n\r\nuser_data' in upload.content
    assert b'filename="upload.mp4"' in upload.content and b"clip.mp4" not in upload.content

    body = json.loads(recorder.requests[1].content)
    assert body["model"] == "muse-spark-1.3"
    assert body["store"] is False
    fmt = body["text"]["format"]
    assert fmt["type"] == "json_schema" and fmt["strict"] is True and fmt["name"]
    assert fmt["schema"] == strict_schema()
    assert "response_format" not in body
    content = body["input"][0]["content"]
    assert content[1] == {"type": "input_file", "file_id": "file-123"}
    assert "수제 머그컵" in content[0]["text"] and "microseconds" in content[0]["text"]
    retry = json.loads(recorder.requests[2].content)["input"][0]["content"][0]["text"]
    assert "hook_candidates: too many items" in retry


def test_strict_schema_meets_the_documented_strict_subset():
    schema = strict_schema()
    assert "policy_flags" not in schema["properties"]

    def walk(node: object) -> None:
        if isinstance(node, dict):
            assert "oneOf" not in node and "allOf" not in node and "default" not in node
            if node.get("type") == "object" and "properties" in node:
                assert node["additionalProperties"] is False
                assert sorted(node["required"]) == sorted(node["properties"])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert "anyOf" in json.dumps(schema)


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={"error": {"type": "authentication_error", "code": "invalid_api_key", "message": "bad LLM_1_secret"}}), "E_API_AUTH"),
        (httpx.Response(403, json={"error": {"type": "permission_error"}}), "E_API_AUTH"),
        (httpx.Response(429, json={"error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}}), "E_API_RATE"),
        (httpx.Response(200, content=b"{not json"), "E_API_SCHEMA"),
        (httpx.Response(200, json=["not", "an", "object"]), "E_API_SCHEMA"),
        (httpx.Response(200, json={"status": "completed", "output": []}), "E_API_SCHEMA"),
        (httpx.Response(200, json={"status": "incomplete", "output": []}), "E_API_INCOMPLETE"),
        (httpx.Response(400, json={"error": {"code": "content_policy_violation"}}), "E_API_REFUSED"),
        (httpx.Response(500, json={"error": {"type": "server_error"}}), "E_API_REMOTE"),
        (httpx.Response(302, headers={"location": "https://example.com/"}), "E_API_REMOTE"),
    ],
)
def test_spark_error_mapping(clip, response, code):
    recorder = Recorder({("POST", "/v1/files"): uploaded, ("POST", "/v1/responses"): lambda r: response})
    with pytest.raises(AdLoomError, match=code) as raised:
        LiveSpark(KEY, recorder.client()).understand(clip, "note", "ko")
    assert raised.value.error.stage == "understand"
    assert "secret" not in str(raised.value) and KEY not in str(raised.value)
    assert raised.value.error.retryable is (code in {"E_API_RATE"} or response.status_code >= 500)


def test_spark_refusal_and_timeout(clip):
    refusal = responses_body("")
    refusal["output"][1]["content"] = [{"type": "refusal", "refusal": "no"}]  # type: ignore[index]
    recorder = Recorder(
        {("POST", "/v1/files"): uploaded, ("POST", "/v1/responses"): lambda r: httpx.Response(200, json=refusal)}
    )
    with pytest.raises(AdLoomError, match="E_API_REFUSED"):
        LiveSpark(KEY, recorder.client()).understand(clip, "note", "ko")

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    recorder = Recorder({("POST", "/v1/files"): timeout})
    with pytest.raises(AdLoomError, match="E_API_NETWORK") as raised:
        LiveSpark(KEY, recorder.client()).understand(clip, "note", "ko")
    assert raised.value.error.retryable is False

    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    recorder = Recorder({("POST", "/v1/files"): refused})
    with pytest.raises(AdLoomError, match="E_API_NETWORK") as raised:
        LiveSpark(KEY, recorder.client()).understand(clip, "note", "ko")
    assert raised.value.error.retryable is True


def test_spark_cleanup_deletes_uploaded_files(clip):
    recorder = Recorder(
        {
            ("POST", "/v1/files"): uploaded,
            ("POST", "/v1/responses"): lambda r: httpx.Response(200, json=responses_body(UNDERSTANDING)),
            ("DELETE", "/v1/files/file-123"): lambda r: httpx.Response(
                200, json={"id": "file-123", "object": "file", "deleted": True}
            ),
        }
    )
    spark = LiveSpark(KEY, recorder.client())
    spark.understand(clip, "note", "en")
    assert spark.api.uploads
    assert spark.cleanup() == ()
    assert spark.api.uploads == {}
    assert recorder.paths()[-1] == "DELETE /v1/files/file-123"


# --- SAM -----------------------------------------------------------------------------


def sam_recorder(body: bytes | Handler) -> Recorder:
    handler = body if callable(body) else event_stream(body)
    return Recorder({("POST", "/v1/files"): uploaded, ("POST", "/v1/responses"): handler})


def test_sam_streams_and_picks_the_object_with_most_frames(clip):
    lines = [
        f"<0f>{OBJ0},{OBJ1}",
        f"<1f>{OBJ0}",
        f"<3f>{OBJ0.replace(';w=320', ';c=0.75;w=320')}",
        f"<2f>{OBJ1}",
    ]
    recorder = sam_recorder(sam_events(lines))
    result = LiveTracking(KEY, recorder.client()).track(clip, "button")

    request = recorder.requests[1]
    assert request.headers["accept"] == "text/event-stream"
    assert request.headers["accept-encoding"] == "identity"
    body = json.loads(request.content)
    assert body["model"] == "sam-3.1" and body["stream"] is True
    assert body["input"][0]["content"] == [
        {"type": "input_text", "text": "button"},
        {"type": "input_video", "file_id": "file-123"},
    ]
    assert body["metadata"] == {"include_confidence": "true", "mask_encoding": "one_bit"}

    assert (result.source_width, result.source_height, result.frame_count) == (320, 334, 6)
    assert (result.fps.numerator, result.fps.denominator) == (30, 1)
    assert [box is not None for box in result.boxes] == [True, True, False, True, False, False]
    assert result.coverage == pytest.approx(3 / 6)
    first = result.boxes[0]
    assert first is not None
    # Inclusive wire x2=270,y2=254 -> half-open right/bottom 271/255 -> 60x27.
    assert (first.x, first.y, first.w, first.h, first.score) == (211, 228, 60, 27, None)
    assert result.boxes[3] is not None and result.boxes[3].score == 0.75


def test_sam_ties_go_to_the_lowest_numeric_object_id(clip):
    later = OBJ0.replace("0<|box", "10<|box", 1)
    lines = [f"<0f>{later},{OBJ1.replace('1<|box', '2<|box', 1)}"]
    result = LiveTracking(KEY, sam_recorder(sam_events(lines)).client()).track(clip, "button")
    assert result.boxes[0] is not None and result.boxes[0].x == 155


@pytest.mark.parametrize("empty_lane", [False, True])
def test_sam_zero_match_is_all_none(clip, empty_lane):
    if empty_lane:
        body = sam_events([])
    else:
        body = sse(
            [
                {"type": "response.created", "response": {}},
                {"type": "response.completed", "response": {"status": "completed"}},
            ]
        )
    result = LiveTracking(KEY, sam_recorder(body).client()).track(clip, "unicorn")
    assert result.boxes == (None,) * 6 and result.coverage == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (sam_events([f"<0f>{OBJ0}"], terminal="response.incomplete"), "E_API_INCOMPLETE"),
        (sam_events([f"<0f>{OBJ0}"], terminal="eof"), "E_API_INCOMPLETE"),
        (sam_events([f"<9f>{OBJ0}"]), "E_API_SCHEMA"),
        (sam_events([f"<0f>{OBJ0.replace('w=320;h=334', 'w=640;h=668')}"]), "E_API_SCHEMA"),
        (sam_events([f"<0f>{OBJ0.replace('data=27,60', 'data=9999,9999')}"]), "E_RESOURCE_LIMIT"),
        (sam_events([f"<0f>{OBJ0.replace('~!!!!M', '~zzzzM')}"]), "E_API_SCHEMA"),
        (
            sse([{"type": "response.failed", "response": {"error": {"code": "server_error", "message": "x"}}}]),
            "E_API_REMOTE",
        ),
        (
            sse([{"type": "error", "error": {"type": "rate_limit_error", "code": "rate_limit_exceeded"}}]),
            "E_API_RATE",
        ),
        (b"data: {not json}\n\n", "E_API_SCHEMA"),
        (b"data: " + b"x" * (2 * 1024 * 1024 + 10) + b"\n\n", "E_RESOURCE_LIMIT"),
    ],
    ids=lambda value: value if isinstance(value, str) else "body",
)
def test_sam_stream_failures(clip, body, code):
    with pytest.raises(AdLoomError, match=code) as raised:
        LiveTracking(KEY, sam_recorder(body).client()).track(clip, "button")
    assert raised.value.error.stage == "track"


def test_sam_refusal_and_http_errors_before_streaming(clip):
    lane = {"item_id": "m", "output_index": 0, "content_index": 0}
    refusal = sse(
        [{"type": "response.content_part.done", **lane, "part": {"type": "refusal", "refusal": "no"}}]
    )
    with pytest.raises(AdLoomError, match="E_API_REFUSED"):
        LiveTracking(KEY, sam_recorder(refusal).client()).track(clip, "button")
    for status, code in ((401, "E_API_AUTH"), (429, "E_API_RATE")):
        recorder = sam_recorder(lambda r, s=status: httpx.Response(s, json={"error": {}}))
        with pytest.raises(AdLoomError, match=code):
            LiveTracking(KEY, recorder.client()).track(clip, "button")
    json_instead = lambda r: httpx.Response(200, json={"status": "completed"})  # noqa: E731
    with pytest.raises(AdLoomError, match="E_API_SCHEMA"):
        LiveTracking(KEY, sam_recorder(json_instead).client()).track(clip, "button")


# --- Image ---------------------------------------------------------------------------


def png_b64(size: tuple[int, int], mode: str = "RGB", fmt: str = "PNG") -> str:
    buffer = io.BytesIO()
    Image.new(mode, size).save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def image_recorder(payload: dict[str, object] | httpx.Response) -> Recorder:
    response = payload if isinstance(payload, httpx.Response) else httpx.Response(200, json=payload)
    return Recorder({("POST", "/v1/images/generations"): lambda r: response})


def test_image_requests_png_without_tools_and_fits_exact_size(tmp_path):
    payload = {"created": 1, "data": [{"b64_json": png_b64((640, 1024))}], "output_format": "png"}
    recorder = image_recorder(payload)
    path = LiveImage(KEY, recorder.client(), output=tmp_path).generate_scene("머그컵", (1080, 1920))
    body = json.loads(recorder.requests[0].content)
    assert body["model"] == "muse-image-1.0"
    assert body["size"] == "1080x1920" and body["n"] == 1
    assert body["response_format"] == "b64_json" and body["output_format"] == "png"
    assert body["tool_enablement"] == {
        "enable_image_search": False, "enable_web_search": False, "enable_shell": False,
    }
    assert "No text" in body["prompt"] and "머그컵" in body["prompt"]
    assert path.parent == tmp_path / "images"
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == (1080, 1920)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"data": [{"b64_json": png_b64((64, 64), fmt="WEBP")}], "output_format": "png"}, "E_API_SCHEMA"),
        ({"data": [{"b64_json": png_b64((64, 64))}], "output_format": "webp"}, "E_API_SCHEMA"),
        ({"data": [{"b64_json": "@@not-base64@@"}]}, "E_API_SCHEMA"),
        ({"data": []}, "E_API_SCHEMA"),
        ({"data": [{"b64_json": png_b64((4097, 4097), mode="1")}]}, "E_RESOURCE_LIMIT"),
        (httpx.Response(200, content=b"<html>"), "E_API_SCHEMA"),
        (httpx.Response(401, json={"error": {"type": "authentication_error"}}), "E_API_AUTH"),
        (httpx.Response(429, json={"error": {"type": "rate_limit_error"}}), "E_API_RATE"),
    ],
    ids=lambda value: value if isinstance(value, str) else "payload",
)
def test_image_failures(tmp_path, payload, code):
    with pytest.raises(AdLoomError, match=code):
        LiveImage(KEY, image_recorder(payload).client(), output=tmp_path).generate_scene("cup", (1080, 1080))
    assert not (tmp_path / "images").exists()


# --- Voice ---------------------------------------------------------------------------


def multipart_parts(request: httpx.Request) -> dict[str, tuple[str, bytes]]:
    head = f"Content-Type: {request.headers['content-type']}\r\n\r\n".encode()
    message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(head + request.content)
    parts = {}
    for part in message.iter_parts():
        parts[part.get_param("name", header="content-disposition")] = (
            part.get_content_type(),
            part.get_payload(decode=True),
        )
    return parts


def test_voice_sends_endpointing_wav_and_converts_turns(tmp_path, tone):
    turns = {
        "sessionId": "s",
        "transcript": "안녕하세요. 수제 머그컵입니다.",
        "audioDurationMs": 1000,
        "turns": [
            {"turnId": 1, "startMs": 120, "endMs": 480, "transcript": " 안녕하세요. "},
            {"turnId": 2, "startMs": 500, "endMs": 900, "transcript": "수제 머그컵입니다."},
            {"turnId": 3, "startMs": 950, "endMs": 1000, "transcript": ""},
        ],
    }
    recorder = Recorder({("POST", "/v1/asr/transcribe"): lambda r: httpx.Response(200, json=turns)})
    segments = LiveVoice(KEY, recorder.client(), job_dir=tmp_path).transcribe(tone, "ko")

    assert [(s.start_us, s.end_us, s.text) for s in segments] == [
        (120_000, 480_000, "안녕하세요."),
        (500_000, 900_000, "수제 머그컵입니다."),
    ]
    request = recorder.requests[0]
    assert request.headers["accept"] == "application/json"
    parts = multipart_parts(request)
    kind, raw = parts["request"]
    assert kind == "application/json"
    assert json.loads(raw) == {
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "mode": "ENDPOINTING",
        "languageBias": ["Korean"],
    }
    kind, audio = parts["audio"]
    assert kind == "audio/wav"
    with wave.open(io.BytesIO(audio)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16_000)
    assert list((tmp_path / "tmp").iterdir()) == []


@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(401, json={"error": {"type": "authentication_error"}}), "E_API_AUTH"),
        (httpx.Response(429, json={"error": {"type": "rate_limit_error"}}), "E_API_RATE"),
        (httpx.Response(413, json={"error": {"code": "payload_too_large"}}), "E_RESOURCE_LIMIT"),
        (httpx.Response(200, content=b"oops"), "E_API_SCHEMA"),
        (httpx.Response(200, json={"transcript": "x"}), "E_API_SCHEMA"),
        (httpx.Response(200, json={"turns": [{"startMs": 5, "endMs": 5, "transcript": "x"}]}), "E_API_SCHEMA"),
    ],
)
def test_voice_failures(tmp_path, tone, response, code):
    recorder = Recorder({("POST", "/v1/asr/transcribe"): lambda r: response})
    with pytest.raises(AdLoomError, match=code):
        LiveVoice(KEY, recorder.client(), job_dir=tmp_path, stage="input").transcribe(tone, "ko")
    assert list((tmp_path / "tmp").iterdir()) == []


def test_voice_timeout_is_a_network_error(tmp_path, tone):
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    recorder = Recorder({("POST", "/v1/asr/transcribe"): timeout})
    with pytest.raises(AdLoomError, match="E_API_NETWORK"):
        LiveVoice(KEY, recorder.client(), job_dir=tmp_path).transcribe(tone, "en")
