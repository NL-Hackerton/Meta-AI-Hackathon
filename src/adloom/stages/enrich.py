import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from adloom.adapters.base import ImageAdapter, VoiceAdapter
from adloom.config import ASPECTS, FONT_PATH, SAFE_BOTTOM, SAFE_TOP, AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import AspectImage, EnrichResult, MediaInfo, Understanding, resolution


def text_image(text: str, size: tuple[int, int], *, bottom: bool = False) -> Image.Image:
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(FONT_PATH), 58)
    font.set_variation_by_axes([600])
    width, height = size
    lines: list[str] = []
    line = ""
    for character in text:
        if draw.textlength(line + character, font=font) > width * 0.82:
            lines.append(line)
            line = character
        else:
            line += character
    if line:
        lines.append(line)
    value = "\n".join(lines)
    bounds = draw.multiline_textbbox((0, 0), value, font=font, spacing=10)
    text_h = bounds[3] - bounds[1]
    top = int(height * SAFE_TOP) + 30
    lower = int(height * (1 - SAFE_BOTTOM)) - 30
    if text_h > lower - top:
        raise AdLoomError("E_INPUT_INVALID", "assemble", "Text exceeds the safe area")
    x = (width - (bounds[2] - bounds[0])) / 2 - bounds[0]
    y = (lower - text_h if bottom else top) - bounds[1]
    draw.rounded_rectangle(
        (width * 0.06, y + bounds[1] - 18, width * 0.94, y + bounds[3] + 18),
        radius=18,
        fill=(10, 20, 20, 215),
    )
    draw.multiline_text((x, y), value, font=font, fill="white", spacing=10, align="center")
    return image


def enrich(
    video: Path,
    media: MediaInfo,
    understanding: Understanding,
    job_dir: Path,
    image: ImageAdapter,
    voice: VoiceAdapter,
) -> EnrichResult:
    directory = job_dir / "enrichment"
    directory.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    thumbnails: list[AspectImage] = []
    endcards: list[AspectImage] = []
    fallback = False
    for aspect in ASPECTS:
        size = resolution(aspect)
        try:
            generated = image.generate_scene(understanding.product_name, size)
            with Image.open(generated) as source:
                background = ImageOps.fit(source.convert("RGB"), size)
        except (AdLoomError, OSError, ValueError):
            fallback = True
            representative = directory / "representative.png"
            if not representative.exists():
                try:
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-v",
                            "error",
                            "-nostdin",
                            "-y",
                            "-i",
                            str(video),
                            "-frames:v",
                            "1",
                            "-threads",
                            "1",
                            str(representative),
                        ],
                        capture_output=True,
                        timeout=30,
                        check=True,
                    )
                except subprocess.SubprocessError:
                    raise AdLoomError(
                        "E_RENDER_FAILED", "enrich", "Representative frame extraction failed"
                    ) from None
            with Image.open(representative) as source:
                background = ImageOps.fit(source.convert("RGB"), size)
        suffix = aspect.replace(":", "x")
        thumbnail = directory / f"thumbnail-{suffix}.png"
        background.save(thumbnail)
        card = (
            Image.new("RGBA", size, (18, 60, 51, 255)) if fallback else background.convert("RGBA")
        )
        cta_text = {"LEARN_MORE": "자세히 보기"}.get(understanding.cta, understanding.cta)
        card.alpha_composite(text_image(cta_text, size))
        endcard = directory / f"endcard-{suffix}.png"
        card.convert("RGB").save(endcard)
        thumbnails.append(
            AspectImage(
                aspect=aspect,
                path=thumbnail.relative_to(job_dir).as_posix(),
                sha256=file_hash(thumbnail),
                origin_mode="fixture",
            )
        )
        endcards.append(
            AspectImage(
                aspect=aspect,
                path=endcard.relative_to(job_dir).as_posix(),
                sha256=file_hash(endcard),
                origin_mode="fixture",
            )
        )
    if fallback:
        warnings.append("Image generation failed; original frame and solid endcard used")
    transcript = voice.transcribe(video, "ko") if media.has_audio else ()
    return EnrichResult(
        source_duration_us=media.duration_us,
        thumbnails=(thumbnails[0], thumbnails[1], thumbnails[2]),
        endcards=(endcards[0], endcards[1], endcards[2]),
        transcript=transcript,
        image_fallback=fallback,
        warnings=tuple(warnings),
    )
