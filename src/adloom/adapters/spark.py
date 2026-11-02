"""Live Muse Spark video understanding through Files + Responses structured output."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import httpx

from adloom.adapters.model_api import ModelApi, build_client, require_standard_model
from adloom.config import ALLOWED_CTAS, MAX_HOOK_CHARS, AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import Understanding

MODEL = "muse-spark-1.3"
SCHEMA_NAME = "adloom_understanding"
# policy_flags is always recomputed locally by adloom.policy, so the model never supplies it.
LOCAL_ONLY_FIELDS = ("policy_flags",)
_DROPPED_KEYWORDS = frozenset({"default", "discriminator", "title"})
_LANGUAGES = {"ko": "Korean", "en": "English"}

INSTRUCTIONS = f"""You plan short vertical video ads for a small business.
Watch the attached video and read the owner's note, then return one JSON object
that matches the provided schema exactly.
Rules:
- source_duration_us is the video duration given in the request, in microseconds.
- key_moments: 1 to 5 ordered, non-overlapping spans inside the video that best
  show the product, in integer microseconds, with a short reason each.
- sam_prompt: a short English noun phrase (ASCII, at most 6 words) naming the
  single main product as it appears on screen, e.g. "white ceramic mug".
  Name the object; do not write an instruction or a list.
- hook_candidates: exactly 3 hooks with ids "a", "b", "c"; each text at most
  {MAX_HOOK_CHARS} characters, written in the requested ad language.
- primary_text (at most 125 characters), headline and product_name (at most 40
  characters) are written in the requested ad language.
- cta must be one of: {", ".join(ALLOWED_CTAS)}.
- claims: list every factual claim your copy makes (price, origin, health,
  awards, superlatives). Classify each as "explicit" (stated in the note),
  "observation" (visible in the video) or "inference". Reference evidence with
  the digests given in the request; use an empty list when there are none.
- Do not invent prices, discounts, awards or health effects that are not in the note."""


def strict_schema(model: type[Understanding] = Understanding) -> dict[str, Any]:
    """Convert the pydantic schema into the Responses strict structured-output subset.

    Strict mode requires every object to list all properties in ``required`` and
    to set ``additionalProperties: false``; ``oneOf``/``allOf`` are not allowed, so
    pydantic's discriminated union is rewritten to ``anyOf``.
    """
    schema = copy.deepcopy(model.model_json_schema())
    for name in LOCAL_ONLY_FIELDS:
        schema["properties"].pop(name, None)
        if name in schema.get("required", []):
            schema["required"].remove(name)
    _strictify(schema)
    return schema


def _strictify(node: object) -> None:
    if isinstance(node, list):
        for item in node:
            _strictify(item)
        return
    if not isinstance(node, dict):
        return
    for keyword in _DROPPED_KEYWORDS & node.keys():
        # A property literally named "title" or "default" lives under "properties", not here.
        del node[keyword]
    if "oneOf" in node:
        node["anyOf"] = node.pop("oneOf")
    if "allOf" in node:
        raise ValueError("allOf is not supported by strict structured output")
    if node.get("type") == "object" and isinstance(node.get("properties"), dict):
        node["required"] = list(node["properties"])
        node["additionalProperties"] = False
    for key, value in node.items():
        if key in ("properties", "$defs") and isinstance(value, dict):
            for child in value.values():
                _strictify(child)
        else:
            _strictify(value)


def probe_duration_us(video: Path) -> int:
    try:
        output = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-protocol_whitelist",
                "file,pipe",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(video),
            ],
            capture_output=True,
            timeout=60,
            check=True,
        ).stdout
        return round(float(json.loads(output)["format"]["duration"]) * 1_000_000)
    except (subprocess.SubprocessError, ValueError, KeyError, TypeError):
        raise AdLoomError("E_INPUT_INVALID", "understand", "Video probe failed") from None


class LiveSpark:
    """UnderstandingAdapter backed by ``muse-spark-1.3`` on the Responses API."""

    def __init__(
        self, api_key: str, client: httpx.Client | None = None, model: str = MODEL
    ) -> None:
        self.model = require_standard_model(model, MODEL, "understand")
        self.api = ModelApi(api_key, client or build_client())
        self.schema = strict_schema()

    def request_body(
        self,
        file_id: str,
        note_text: str,
        language: str,
        duration_us: int,
        video_sha256: str,
        feedback: str | None,
    ) -> dict[str, object]:
        if language not in _LANGUAGES:
            raise AdLoomError("E_INPUT_INVALID", "understand", "Unsupported ad language")
        note_sha256 = hashlib.sha256(note_text.encode("utf-8")).hexdigest()
        text = (
            f"Ad language: {_LANGUAGES[language]}\n"
            f"Video duration: {duration_us} microseconds\n"
            f"Video evidence digest: {video_sha256}\n"
            f"Owner note digest: {note_sha256}\n"
            f"Owner note:\n{note_text}"
        )
        if feedback is not None:
            text += (
                "\n\nYour previous answer failed validation with this error:\n"
                f"{feedback}\nReturn a corrected JSON object."
            )
        return {
            "model": self.model,
            "store": False,
            "instructions": INSTRUCTIONS,
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": text},
                        {"type": "input_file", "file_id": file_id},
                    ],
                }
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": SCHEMA_NAME,
                    "schema": self.schema,
                    "strict": True,
                }
            },
        }

    def understand(
        self, video: Path, note_text: str, language: str, feedback: str | None = None
    ) -> str:
        duration_us = probe_duration_us(video)
        file_id = self.api.upload_file(video, "video/mp4", "understand")
        body = self.request_body(
            file_id, note_text, language, duration_us, file_hash(video), feedback
        )
        response = self.api.post_json("/responses", body, "understand", "Spark response")
        return output_text(response)

    def cleanup(self) -> tuple[str, ...]:
        """Delete uploaded videos; return remote ids whose deletion failed."""
        return self.api.delete_uploads("understand")


def output_text(response: dict[str, Any]) -> str:
    status = response.get("status")
    if status == "incomplete":
        raise AdLoomError("E_API_INCOMPLETE", "understand", "Spark response is incomplete")
    if status != "completed":
        raise AdLoomError("E_API_SCHEMA", "understand", "Spark response is not completed")
    output = response.get("output")
    if not isinstance(output, list):
        raise AdLoomError("E_API_SCHEMA", "understand", "Spark response has no output list")
    texts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            raise AdLoomError("E_API_SCHEMA", "understand", "Spark message has no content")
        for part in content:
            kind = part.get("type") if isinstance(part, dict) else None
            if kind == "refusal":
                raise AdLoomError("E_API_REFUSED", "understand", "Spark refused the request")
            if kind == "output_text":
                text = part.get("text")
                if not isinstance(text, str):
                    raise AdLoomError("E_API_SCHEMA", "understand", "Spark output text is invalid")
                texts.append(text)
    if not texts:
        raise AdLoomError("E_API_SCHEMA", "understand", "Spark response has no output text")
    return "".join(texts)
