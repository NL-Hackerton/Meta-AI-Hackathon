"""Live Muse Image scene generation through ``/v1/images/generations``."""

import base64
import binascii
import hashlib
import io
import warnings
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from adloom.adapters.model_api import ModelApi, build_client, require_standard_model
from adloom.config import AdLoomError
from adloom.jobs import atomic_write

MODEL = "muse-image-1.0"
MAX_PIXELS = 16_777_216
MAX_ASPECT = 16
TOOLS_DISABLED = {
    "enable_image_search": False,
    "enable_web_search": False,
    "enable_shell": False,
}
# Every visible word is drawn by code later, so the model is asked for a text-free scene.
PROMPT_TEMPLATE = (
    "Background scene for a short advertisement about: {subject}. "
    "Photographic, clean composition with empty space. "
    "No text, no letters, no numbers, no logos, no watermarks."
)


class LiveImage:
    """ImageAdapter backed by ``muse-image-1.0``; writes exact-size PNGs under ``output``."""

    def __init__(
        self,
        api_key: str,
        client: httpx.Client | None = None,
        output: Path | None = None,
        model: str = MODEL,
    ) -> None:
        if output is None:
            raise AdLoomError("E_INPUT_INVALID", "enrich", "Image output directory is required")
        self.model = require_standard_model(model, MODEL, "enrich")
        self.api = ModelApi(api_key, client or build_client())
        self.output = output

    def request_body(self, prompt: str, size: tuple[int, int]) -> dict[str, object]:
        return {
            "model": self.model,
            "prompt": PROMPT_TEMPLATE.format(subject=prompt.strip()),
            "n": 1,
            # The API treats size as an aspect ratio, not exact pixels.
            "size": f"{size[0]}x{size[1]}",
            "response_format": "b64_json",
            "output_format": "png",
            "tool_enablement": dict(TOOLS_DISABLED),
        }

    def generate_scene(self, prompt: str, size: tuple[int, int]) -> Path:
        width, height = size
        if width <= 0 or height <= 0 or max(width, height) > MAX_ASPECT * min(width, height):
            raise AdLoomError("E_INPUT_INVALID", "enrich", "Unsupported image size")
        if width * height > MAX_PIXELS:
            raise AdLoomError("E_RESOURCE_LIMIT", "enrich", "Requested image is too large")
        if not prompt.strip():
            raise AdLoomError("E_INPUT_INVALID", "enrich", "Image prompt is empty")
        response = self.api.post_json(
            "/images/generations", self.request_body(prompt, size), "enrich", "Image generation"
        )
        image = fit_png(decode_png(response), size)
        digest = hashlib.sha256(f"{prompt}:{size}".encode()).hexdigest()
        path = self.output / "images" / f"{digest}.png"
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        atomic_write(path, buffer.getvalue())
        return path


def decode_png(response: dict[str, object]) -> Image.Image:
    data = response.get("data")
    if response.get("output_format") not in (None, "png"):
        raise AdLoomError("E_API_SCHEMA", "enrich", "Image response is not PNG")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise AdLoomError("E_API_SCHEMA", "enrich", "Image response must hold one image")
    encoded = data[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded:
        raise AdLoomError("E_API_SCHEMA", "enrich", "Image response has no base64 payload")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise AdLoomError("E_API_SCHEMA", "enrich", "Image payload is not base64") from None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(raw))
            if image.format != "PNG":
                raise AdLoomError("E_API_SCHEMA", "enrich", "Image payload is not PNG")
            if image.width * image.height > MAX_PIXELS:
                raise AdLoomError("E_RESOURCE_LIMIT", "enrich", "Generated image is too large")
            image.load()
    except (Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise AdLoomError("E_RESOURCE_LIMIT", "enrich", "Generated image is too large") from None
    except (OSError, SyntaxError, ValueError):
        raise AdLoomError("E_API_SCHEMA", "enrich", "Image payload cannot be decoded") from None
    return image


def fit_png(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Scale and center-crop to exactly ``size`` (the API only honours the aspect ratio)."""
    rgb = image.convert("RGB")
    if rgb.size == size:
        return rgb
    return ImageOps.fit(rgb, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
