"""Deterministic ffmpeg assembly from validated local sources and crop plans."""

import hashlib
import subprocess
from pathlib import Path

from adloom.config import FONT_PATH, AdLoomError
from adloom.jobs import file_hash
from adloom.schemas import (
    CropPlan,
    Hook,
    MediaInfo,
    Moment,
    RenderedVariant,
    RenderPlan,
    Segment,
    TimelinePlan,
    TimelineSpan,
    resolution,
)
from adloom.stages.enrich import text_image
from adloom.stages.input import probe


def plan_timeline(media: MediaInfo, moments: tuple[Moment, ...]) -> TimelinePlan:
    spans: list[TimelineSpan] = []
    end = 0
    for moment in moments:
        duration = min(moment.end_us - moment.start_us, 28_000_000 - end)
        if duration <= 0:
            break
        spans.append(
            TimelineSpan(
                source_start_us=moment.start_us,
                source_end_us=moment.start_us + duration,
                output_start_us=end,
                output_end_us=end + duration,
            )
        )
        end += duration
    repeat = 0
    while end < 6_000_000:
        repeat += 1
        duration = min(media.duration_us, 6_000_000 - end)
        spans.append(
            TimelineSpan(
                source_start_us=0,
                source_end_us=duration,
                output_start_us=end,
                output_end_us=end + duration,
                repeat_index=repeat,
            )
        )
        end += duration
    return TimelinePlan(
        source_sha256=media.normalized_sha256,
        source_duration_us=media.duration_us,
        spans=tuple(spans),
    )


def map_subtitles(timeline: TimelinePlan, transcript: tuple[Segment, ...]) -> tuple[Segment, ...]:
    result = []
    for span in timeline.spans:
        for segment in transcript:
            start, end = (
                max(span.source_start_us, segment.start_us),
                min(span.source_end_us, segment.end_us),
            )
            if start < end:
                result.append(
                    Segment(
                        start_us=span.output_start_us + start - span.source_start_us,
                        end_us=span.output_start_us + end - span.source_start_us,
                        text=segment.text,
                    )
                )
    return tuple(result)


def renderer_fingerprint() -> str:
    version = subprocess.check_output(["ffmpeg", "-version"])
    overlay_code = (Path(__file__).parent / "stages/enrich.py").read_bytes()
    return hashlib.sha256(
        version + Path(__file__).read_bytes() + overlay_code + FONT_PATH.read_bytes()
    ).hexdigest()


def _local(root: Path, relative: str) -> Path:
    result = (root / relative).resolve()
    if not result.is_relative_to(root.resolve()) or not result.is_file():
        raise AdLoomError("E_RENDER_FAILED", "assemble", "Render source is not a local job asset")
    return result


def frame_hash(path: Path) -> str:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-map",
            "0:v:0",
            "-threads",
            "1",
            "-f",
            "framemd5",
            "-",
        ],
        capture_output=True,
        check=True,
        timeout=180,
    )
    return hashlib.sha256(result.stdout).hexdigest()


def render_variant(root: Path, plan: RenderPlan, crop: CropPlan, hook: Hook) -> RenderedVariant:
    root = root.resolve()
    output_dir = root / "renders" / f"r{plan.revision:06d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    name = f"{crop.aspect.replace(':', 'x')}-{hook.id}"
    width, height = resolution(crop.aspect)
    fps = f"{plan.media.fps.numerator}/{plan.media.fps.denominator}"
    source = next(s for s in plan.sources if s.media_type == "video")
    card = next(image for image in plan.enrichment.endcards if image.aspect == crop.aspect)
    hook_path = output_dir / f"{name}-hook.png"
    text_image(hook.text, (width, height)).save(hook_path)
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-protocol_whitelist",
        "file,pipe",
        "-i",
        str(_local(root, source.path)),
        "-loop",
        "1",
        "-framerate",
        fps,
        "-i",
        str(_local(root, card.path)),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-i",
        str(hook_path),
    ]
    crop_file = output_dir / f"{name}-crop.txt"
    crop_file.write_text(
        "\n".join(
            f"{i * plan.media.fps.denominator / plan.media.fps.numerator:.9f} crop@follow x {r.x:g}, crop@follow y {r.y:g};"
            for i, r in enumerate(crop.rects)
        )
    )
    first = crop.rects[0]
    count = len(plan.timeline.spans)
    filters = [
        f"[0:v]sendcmd=f={crop_file.relative_to(root).as_posix()},"
        f"crop@follow={first.w:g}:{first.h:g}:{first.x:g}:{first.y:g},"
        f"scale={width}:{height},setsar=1,split={count}" + "".join(f"[s{i}]" for i in range(count)),
        f"[1:v]scale={width}:{height},setsar=1,trim=duration=2,setpts=PTS-STARTPTS[card]",
    ]
    if plan.media.has_audio:
        filters += [
            f"[0:a]aresample=44100,apad,asplit={count}" + "".join(f"[a{i}]" for i in range(count)),
            "[2:a]atrim=duration=2,asetpts=PTS-STARTPTS[cardaudio]",
        ]
    else:
        filters += [
            f"[2:a]asplit={count + 1}" + "".join(f"[a{i}]" for i in range(count)) + "[silence]",
            "[silence]atrim=duration=2,asetpts=PTS-STARTPTS[cardaudio]",
        ]
    for i, span in enumerate(plan.timeline.spans):
        start, end = span.source_start_us / 1_000_000, span.source_end_us / 1_000_000
        filters += [
            f"[s{i}]trim=start={start:.6f}:end={end:.6f},setpts=PTS-STARTPTS[v{i}]",
            f"[a{i}]atrim=start={start:.6f}:end={end:.6f},asetpts=PTS-STARTPTS[au{i}]",
        ]
    filters += [
        "".join(f"[v{i}][au{i}]" for i in range(count))
        + f"[card][cardaudio]concat=n={count + 1}:v=1:a=1[body][audio]",
        "[body][3:v]overlay=enable='lt(t,3)'[overlay0]",
    ]
    subtitles = map_subtitles(plan.timeline, plan.enrichment.transcript)
    for index, segment in enumerate(subtitles):
        path = output_dir / f"{name}-subtitle-{index}.png"
        text_image(segment.text, (width, height), bottom=True).save(path)
        command += ["-i", str(path)]
        filters.append(
            f"[overlay{index}][{index + 4}:v]overlay="
            f"enable='gte(t,{segment.start_us / 1e6:.6f})*lt(t,{segment.end_us / 1e6:.6f})'[overlay{index + 1}]"
        )
    script = output_dir / f"{name}.filter"
    script.write_text(";\n".join(filters))
    output = output_dir / f"{name}.mp4"
    command += [
        "-/filter_complex",
        str(script),
        "-map",
        f"[overlay{len(subtitles)}]",
        "-map",
        "[audio]",
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-r",
        fps,
        "-threads",
        "1",
        "-filter_complex_threads",
        "1",
        "-fflags",
        "+bitexact",
        "-flags:v",
        "+bitexact",
        "-flags:a",
        "+bitexact",
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        "-t",
        f"{plan.timeline.duration_us / 1e6:.6f}",
        str(output),
    ]
    for attempt in range(2):
        try:
            subprocess.run(command, cwd=root, capture_output=True, check=True, timeout=300)
            break
        except subprocess.SubprocessError as error:
            if attempt:
                detail = getattr(error, "stderr", b"") or b"render timed out"
                (output_dir / f"{name}.error.log").write_bytes(detail[-8192:])
                raise AdLoomError(
                    "E_RENDER_FAILED", "assemble", "ffmpeg failed; see job render log"
                ) from None
    info = probe(output)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    if (
        video["codec_name"],
        video["pix_fmt"],
        audio["codec_name"],
        video["width"],
        video["height"],
    ) != ("h264", "yuv420p", "aac", width, height):
        raise AdLoomError(
            "E_RENDER_FAILED", "assemble", "Encoded output does not match the render contract"
        )
    if abs(float(info["format"]["duration"]) - plan.timeline.duration_us / 1e6) > 0.1:
        raise AdLoomError(
            "E_RENDER_FAILED", "assemble", "Encoded duration differs from the timeline"
        )
    return RenderedVariant(
        aspect=crop.aspect,
        hook_id=hook.id,
        path=output.relative_to(root).as_posix(),
        sha256=file_hash(output),
        frame_hash=frame_hash(output),
        duration_us=plan.timeline.duration_us,
        width=width,
        height=height,
        origin_mode="fixture",
    )


def render(root: Path, plan: RenderPlan) -> tuple[RenderedVariant, ...]:
    if (
        file_hash(FONT_PATH) != plan.font_sha256
        or renderer_fingerprint() != plan.renderer_fingerprint
    ):
        raise AdLoomError("E_RENDER_FAILED", "assemble", "Font or renderer changed since planning")
    for source in plan.sources:
        if file_hash(_local(root, source.path)) != source.sha256:
            raise AdLoomError("E_RENDER_FAILED", "assemble", "Render source digest mismatch")
    return tuple(
        render_variant(root, plan, crop, hook) for crop in plan.crop_plans for hook in plan.hooks
    )
