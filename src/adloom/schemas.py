"""Immutable, I/O-free contracts shared by AdLoom's services and adapters.

All times are integer microseconds; rectangles and intervals are half-open.
Filesystem containment, provider permissions and human authentication are service
responsibilities, not facts established by deserializing these models.
"""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Literal, Self, get_origin

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    field_validator,
    model_validator,
)

MIN_INPUT_US = 3_000_000
MAX_INPUT_US = 45_000_000
MIN_BODY_US = 6_000_000
MAX_BODY_US = 28_000_000
ENDCARD_US: Literal[2_000_000] = 2_000_000
MAX_AD_US = MAX_BODY_US + ENDCARD_US


def _nfc(value: object) -> object:
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("text must not be blank")
    return value


def _relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or path.as_posix() != value
        or any(part in {".", ".."} for part in value.split("/"))
        or any(character in value for character in ("\\", ":", "%", "?", "#"))
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("path must be a canonical job-relative POSIX path")
    return value


def _utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value.astimezone(UTC)


def _iso_datetime(value: object) -> object:
    return datetime.fromisoformat(value) if isinstance(value, str) else value


NonEmpty = Annotated[str, BeforeValidator(_nfc), AfterValidator(_not_blank)]
NoteText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=200),
    BeforeValidator(_nfc),
    AfterValidator(_not_blank),
]
HookText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=22),
    BeforeValidator(_nfc),
    AfterValidator(_not_blank),
]
Headline = Annotated[
    str,
    StringConstraints(min_length=1, max_length=40),
    BeforeValidator(_nfc),
    AfterValidator(_not_blank),
]
PrimaryText = Annotated[
    str,
    StringConstraints(min_length=1, max_length=125),
    BeforeValidator(_nfc),
    AfterValidator(_not_blank),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{32}$")]
ObjectId = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)$")]
HookId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,31}$")]
RelativePath = Annotated[str, AfterValidator(_relative_path)]
PositiveInt = Annotated[int, Field(gt=0, le=9_007_199_254_740_991)]
NonNegativeInt = Annotated[int, Field(ge=0, le=9_007_199_254_740_991)]
PositiveFloat = Annotated[float, Field(gt=0)]
Probability = Annotated[float, Field(ge=0, le=1)]
UTCDateTime = Annotated[datetime, BeforeValidator(_iso_datetime), AfterValidator(_utc)]
Cta = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
Aspect = Literal["9:16", "4:5", "1:1"]
ExecutionMode = Literal["fixture", "live"]
Stage = Literal["input", "understand", "track", "enrich", "assemble", "publish"]
JobState = Literal[
    "CREATED",
    "UNDERSTOOD",
    "TRACKED",
    "ENRICHED",
    "RENDERED",
    "AWAITING_APPROVAL",
    "APPROVED",
    "PUBLISHED_PAUSED",
    "FAILED",
]
RunState = Literal["IDLE", "RUNNING", "CANCEL_REQUESTED", "INTERRUPTED"]
ProviderModel = Literal[
    "muse-spark-1.3",
    "sam-3.1",
    "muse-image-1.0",
    "muse-voice-transcribe-1.0",
]
ErrorCode = Literal[
    "E_INPUT_INVALID",
    "E_API_AUTH",
    "E_API_RATE",
    "E_API_SCHEMA",
    "E_TRACK_LOW_COVERAGE",
    "E_POLICY_BLOCK",
    "E_RENDER_FAILED",
    "E_PUBLISH_PARTIAL",
    "E_APPROVAL_REQUIRED",
    "E_JOB_BUSY",
    "E_REVISION_CONFLICT",
    "E_STATE_CONFLICT",
    "E_API_NETWORK",
    "E_RESOURCE_LIMIT",
    "E_API_REFUSED",
    "E_API_REMOTE",
    "E_API_INCOMPLETE",
]


def resolution(aspect: Aspect) -> tuple[int, int]:
    return 1080, {"9:16": 1920, "4:5": 1350, "1:1": 1080}[aspect]


class DomainModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
        validate_default=True,
        revalidate_instances="always",
    )

    @model_validator(mode="before")
    @classmethod
    def freeze_json_arrays(cls, value: object) -> object:
        # Normalize only declared tuple fields; never decorate union discriminator fields.
        if not isinstance(value, dict):
            return value
        normalized = None
        for name, field in cls.model_fields.items():
            item = value.get(name)
            if isinstance(item, list) and get_origin(field.annotation) is tuple:
                if normalized is None:
                    normalized = dict(value)
                normalized[name] = tuple(item)
        return value if normalized is None else normalized


class ErrorDetail(DomainModel):
    code: ErrorCode
    stage: Stage
    retryable: bool
    detail: NonEmpty


class FrameRate(DomainModel):
    numerator: PositiveInt
    denominator: PositiveInt

    @model_validator(mode="after")
    def reduced(self) -> Self:
        if math.gcd(self.numerator, self.denominator) != 1:
            raise ValueError("frame rate must be a reduced positive rational")
        return self


class MediaInfo(DomainModel):
    source_sha256: Sha256
    normalized_sha256: Sha256
    source_width: Annotated[int, Field(gt=0, le=4096)]
    source_height: Annotated[int, Field(gt=0, le=4096)]
    duration_us: Annotated[int, Field(ge=MIN_INPUT_US, le=MAX_INPUT_US)]
    fps: FrameRate
    frame_count: Annotated[int, Field(gt=0, le=1350)]
    has_audio: bool

    @model_validator(mode="after")
    def normalized_media(self) -> Self:
        if self.source_width * self.source_height > 8_847_360:
            raise ValueError("normalized media exceeds the pixel limit")
        if self.fps.numerator > 30 * self.fps.denominator:
            raise ValueError("normalized frame rate must not exceed 30 fps")
        frame_us_numerator = 1_000_000 * self.fps.denominator
        difference = abs(
            self.frame_count * frame_us_numerator - self.duration_us * self.fps.numerator
        )
        if difference > frame_us_numerator:
            raise ValueError("duration and frame count differ by more than one frame")
        if self.duration_us * self.fps.numerator > self.frame_count * frame_us_numerator:
            raise ValueError("duration extends past the last normalized frame")
        return self


class NoteDocument(DomainModel):
    text: NoteText

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


class Brief(DomainModel):
    video_path: RelativePath
    note_text: NoteText | None = None
    note_audio_path: RelativePath | None = None
    region: NonEmpty
    daily_budget_krw: PositiveInt
    language: Literal["ko", "en"] = "ko"
    destination_url: HttpUrl | None = None

    @model_validator(mode="after")
    def input_sources(self) -> Self:
        if PurePosixPath(self.video_path).suffix.lower() not in {".mp4", ".mov"}:
            raise ValueError("input video must have an mp4 or mov suffix")
        if self.note_text is None and self.note_audio_path is None:
            raise ValueError("text or audio explanation is required")
        if self.destination_url is not None and (
            self.destination_url.username is not None or self.destination_url.password is not None
        ):
            raise ValueError("destination URL must not contain credentials")
        return self


class InputBundle(DomainModel):
    brief: Brief
    media: MediaInfo


class TimeSpan(DomainModel):
    start_us: NonNegativeInt
    end_us: PositiveInt

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start_us >= self.end_us:
            raise ValueError("time interval must be nonempty and half-open")
        return self


class Moment(TimeSpan):
    reason: NonEmpty


class Segment(TimeSpan):
    text: NonEmpty


class Hook(DomainModel):
    id: HookId
    text: HookText


class Flag(DomainModel):
    field: NonEmpty
    original: NonEmpty
    rule_id: NonEmpty
    severity: Literal["warn", "block"]
    rewrite: NonEmpty


class NoteEvidence(DomainModel):
    kind: Literal["note"] = "note"
    source_digest: Sha256
    start: NonNegativeInt
    end: PositiveInt
    quote: NonEmpty

    @model_validator(mode="after")
    def ordered_span(self) -> Self:
        if self.start >= self.end:
            raise ValueError("note span must be nonempty")
        return self


class VideoEvidence(TimeSpan):
    kind: Literal["video"] = "video"
    source_digest: Sha256


EvidenceRef = Annotated[NoteEvidence | VideoEvidence, Field(discriminator="kind")]
EvidenceReason = Literal["source_unavailable", "source_mismatch", "out_of_bounds", "quote_mismatch"]


class EvidenceAssessment(DomainModel):
    id: NonEmpty
    reference: EvidenceRef
    valid: bool
    reason: EvidenceReason | None = None

    @model_validator(mode="after")
    def consistent_result(self) -> Self:
        if self.valid != (self.reason is None):
            raise ValueError("invalid evidence requires a reason; valid evidence must not have one")
        return self


def assess_evidence(
    evidence_id: str,
    reference: NoteEvidence | VideoEvidence,
    *,
    note: NoteDocument | None = None,
    media: MediaInfo | None = None,
) -> EvidenceAssessment:
    """Check reference identity and bounds, not the truth of the associated claim."""
    reason: EvidenceReason | None = None
    if isinstance(reference, NoteEvidence):
        if note is None:
            reason = "source_unavailable"
        elif reference.source_digest != note.sha256:
            reason = "source_mismatch"
        elif reference.end > len(note.text):
            reason = "out_of_bounds"
        elif note.text[reference.start : reference.end] != reference.quote:
            reason = "quote_mismatch"
    elif media is None:
        reason = "source_unavailable"
    elif reference.source_digest != media.normalized_sha256:
        reason = "source_mismatch"
    elif reference.end_us > media.duration_us:
        reason = "out_of_bounds"
    return EvidenceAssessment(
        id=evidence_id, reference=reference, valid=reason is None, reason=reason
    )


class ClaimCandidate(DomainModel):
    """Provider-facing shape: intentionally has no actor or review decision."""

    id: NonEmpty
    text: NonEmpty
    classification: Literal["explicit", "observation", "inference"]
    references: tuple[EvidenceRef, ...] = ()


class ClaimReview(DomainModel):
    id: NonEmpty
    text: NonEmpty
    classification: Literal["explicit", "observation", "inference"]
    high_risk: bool = False
    reference_ids: tuple[NonEmpty, ...] = ()
    status: Literal["pending", "accepted", "rejected"] = "pending"
    actor: NonEmpty | None = None

    @model_validator(mode="after")
    def human_decision(self) -> Self:
        if (self.status == "pending") != (self.actor is None):
            raise ValueError("only completed review decisions have an actor")
        if len(set(self.reference_ids)) != len(self.reference_ids):
            raise ValueError("duplicate evidence references")
        return self


class Understanding(DomainModel):
    source_duration_us: Annotated[int, Field(ge=MIN_INPUT_US, le=MAX_INPUT_US)]
    product_name: Headline
    sam_prompt: NonEmpty
    key_moments: Annotated[tuple[Moment, ...], Field(min_length=1, max_length=5)]
    hook_candidates: Annotated[tuple[Hook, ...], Field(min_length=3, max_length=3)]
    primary_text: PrimaryText
    headline: Headline
    cta: Cta
    policy_flags: tuple[Flag, ...] = ()
    claims: tuple[ClaimCandidate, ...] = ()

    @model_validator(mode="after")
    def coherent_understanding(self) -> Self:
        if not self.sam_prompt.isascii() or len(self.sam_prompt.split()) > 6:
            raise ValueError("SAM prompt must be an ASCII phrase of at most six words")
        previous_end = 0
        for moment in self.key_moments:
            if moment.start_us < previous_end or moment.end_us > self.source_duration_us:
                raise ValueError(
                    "key moments must be ordered, non-overlapping and inside the source"
                )
            previous_end = moment.end_us
        if len({hook.id for hook in self.hook_candidates}) != 3:
            raise ValueError("hook IDs must be unique")
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("claim IDs must be unique")
        return self


class Rect(DomainModel):
    x: Annotated[float, Field(ge=0)]
    y: Annotated[float, Field(ge=0)]
    w: PositiveFloat
    h: PositiveFloat

    def inside(self, width: int, height: int) -> bool:
        return self.x + self.w <= width and self.y + self.h <= height


class BBox(Rect):
    score: Probability | None = None


class TrackResult(DomainModel):
    source_width: PositiveInt
    source_height: PositiveInt
    fps: FrameRate
    frame_count: Annotated[int, Field(gt=0, le=1350)]
    boxes: tuple[BBox | None, ...]
    coverage: Probability

    @model_validator(mode="after")
    def measured_coverage(self) -> Self:
        if len(self.boxes) != self.frame_count:
            raise ValueError("boxes must have exactly frame_count entries")
        detected = 0
        for box in self.boxes:
            if box is not None:
                if not box.inside(self.source_width, self.source_height):
                    raise ValueError("box is outside the normalized source")
                detected += 1
        if not math.isclose(self.coverage, detected / self.frame_count, rel_tol=0, abs_tol=1e-12):
            raise ValueError("coverage must count detected boxes before interpolation")
        return self


class ObjectTrack(DomainModel):
    object_id: ObjectId
    track: TrackResult


class TrackCandidates(DomainModel):
    tracks: tuple[ObjectTrack, ...]
    selected_object_id: ObjectId | None = None

    @model_validator(mode="after")
    def available_selection(self) -> Self:
        ids = {item.object_id for item in self.tracks}
        if len(ids) != len(self.tracks):
            raise ValueError("duplicate object ID")
        if self.selected_object_id is not None and self.selected_object_id not in ids:
            raise ValueError("selected object is not a returned candidate")
        if self.tracks:
            reference = self.tracks[0].track
            for item in self.tracks[1:]:
                candidate = item.track
                if (
                    candidate.source_width != reference.source_width
                    or candidate.source_height != reference.source_height
                    or candidate.fps != reference.fps
                    or candidate.frame_count != reference.frame_count
                ):
                    raise ValueError("candidate tracks must share normalized media geometry")
        return self


class CropPlan(DomainModel):
    aspect: Aspect
    source_width: PositiveInt
    source_height: PositiveInt
    frame_count: Annotated[int, Field(gt=0, le=1350)]
    max_step_px: PositiveFloat
    rects: tuple[Rect, ...]
    degraded: bool = False
    clipped_frames: tuple[NonNegativeInt, ...] = ()
    safe_area_violation_frames: tuple[NonNegativeInt, ...] = ()

    @model_validator(mode="after")
    def bounded_crop(self) -> Self:
        if len(self.rects) != self.frame_count:
            raise ValueError("crop plan must contain one rectangle per frame")
        width, height = resolution(self.aspect)
        first = self.rects[0]
        if abs(first.w - first.h * width / height) > 1:
            raise ValueError("crop aspect must be within one source pixel of the target")
        previous = first
        for rect in self.rects:
            if (rect.w, rect.h) != (first.w, first.h):
                raise ValueError("crop dimensions must be fixed across frames")
            if not rect.inside(self.source_width, self.source_height):
                raise ValueError("crop rectangle is outside the source")
            if max(abs(rect.x - previous.x), abs(rect.y - previous.y)) > self.max_step_px:
                raise ValueError("crop exceeds the per-axis movement bound")
            previous = rect
        for frames in (self.clipped_frames, self.safe_area_violation_frames):
            if tuple(sorted(set(frames))) != frames or any(i >= self.frame_count for i in frames):
                raise ValueError("quality frame indices must be unique, ordered and in range")
        return self


class TimelineSpan(DomainModel):
    source_start_us: NonNegativeInt
    source_end_us: PositiveInt
    output_start_us: NonNegativeInt
    output_end_us: PositiveInt
    repeat_index: NonNegativeInt = 0

    @model_validator(mode="after")
    def preserve_duration(self) -> Self:
        source_duration = self.source_end_us - self.source_start_us
        output_duration = self.output_end_us - self.output_start_us
        if source_duration <= 0 or source_duration != output_duration:
            raise ValueError("timeline span must preserve a positive source duration")
        return self


class TimelinePlan(DomainModel):
    source_sha256: Sha256
    source_duration_us: Annotated[int, Field(ge=MIN_INPUT_US, le=MAX_INPUT_US)]
    spans: Annotated[tuple[TimelineSpan, ...], Field(min_length=1)]
    endcard_duration_us: Literal[2_000_000] = ENDCARD_US

    @model_validator(mode="after")
    def complete_timeline(self) -> Self:
        end = 0
        repeat = 0
        previous_source_end = 0
        for span in self.spans:
            if span.output_start_us != end or span.source_end_us > self.source_duration_us:
                raise ValueError("timeline must be contiguous and inside the source")
            if span.repeat_index != repeat:
                if span.repeat_index != repeat + 1 or end == 0 or end >= MIN_BODY_US:
                    raise ValueError("repeat passes must be sequential and only pad a short body")
                repeat += 1
                previous_source_end = 0
            if span.source_start_us < previous_source_end:
                raise ValueError("source spans must be ordered and non-overlapping within a pass")
            if repeat and span.source_start_us != previous_source_end:
                raise ValueError("padding must repeat a contiguous prefix of the source")
            previous_source_end = span.source_end_us
            end = span.output_end_us
        if not MIN_BODY_US <= end <= MAX_BODY_US:
            raise ValueError("body must be 6 to 28 seconds after padding")
        if repeat and end != MIN_BODY_US:
            raise ValueError("padding must stop when the body reaches six seconds")
        return self

    @property
    def duration_us(self) -> int:
        return self.spans[-1].output_end_us + self.endcard_duration_us


class Provenance(DomainModel):
    mode: ExecutionMode
    stage: Stage
    kind: Literal["input", "provider", "render", "local_fallback", "skipped"]
    model: ProviderModel | None = None
    capture_id: NonEmpty | None = None
    reason: NonEmpty | None = None

    @model_validator(mode="after")
    def declared_origin(self) -> Self:
        allowed: dict[Stage, set[str]] = {
            "input": {"muse-voice-transcribe-1.0"},
            "understand": {"muse-spark-1.3"},
            "track": {"sam-3.1"},
            "enrich": {"muse-image-1.0", "muse-voice-transcribe-1.0"},
            "assemble": set(),
            "publish": set(),
        }
        if self.model is not None and self.model not in allowed[self.stage]:
            raise ValueError("provider model does not match its stage")
        if self.kind == "provider":
            if self.model is None or self.capture_id is None:
                raise ValueError("provider provenance requires model and capture ID")
        elif self.kind in {"local_fallback", "skipped"}:
            if self.reason is None:
                raise ValueError("fallback or skip requires an explicit reason")
            if self.kind == "local_fallback" and (
                self.stage != "enrich" or self.model != "muse-image-1.0"
            ):
                raise ValueError("only Image enrichment has an allowed local fallback")
        elif self.model is not None or self.capture_id is not None:
            raise ValueError("local assets cannot claim a provider capture")
        return self


class ArtifactRef(DomainModel):
    path: RelativePath
    sha256: Sha256


class ArtifactRecord(ArtifactRef):
    kind: NonEmpty
    stage: Stage
    revision: PositiveInt
    provenance: Provenance

    @model_validator(mode="after")
    def matching_stage(self) -> Self:
        if self.provenance.stage != self.stage:
            raise ValueError("artifact and provenance stages disagree")
        return self


class RenderSource(ArtifactRef):
    source_type: Literal["input_video", "user_photo", "muse_image"]
    media_type: Literal["video", "image"]

    @model_validator(mode="after")
    def allowed_content(self) -> Self:
        if self.media_type == "video" and self.source_type != "input_video":
            raise ValueError("only the input video may supply video frames")
        return self


class AspectImage(ArtifactRef):
    aspect: Aspect
    origin_mode: ExecutionMode

    @field_validator("path")
    @classmethod
    def png_only(cls, value: str) -> str:
        if PurePosixPath(value).suffix.lower() != ".png":
            raise ValueError("internal images must be PNG")
        return value


class EnrichResult(DomainModel):
    source_duration_us: Annotated[int, Field(ge=MIN_INPUT_US, le=MAX_INPUT_US)]
    thumbnails: tuple[AspectImage, AspectImage, AspectImage]
    endcards: tuple[AspectImage, AspectImage, AspectImage]
    transcript: tuple[Segment, ...] = ()
    image_fallback: bool = False
    warnings: tuple[NonEmpty, ...] = ()

    @model_validator(mode="after")
    def complete_enrichment(self) -> Self:
        for images in (self.thumbnails, self.endcards):
            if {image.aspect for image in images} != {"9:16", "4:5", "1:1"}:
                raise ValueError("images must cover all three aspects")
        if self.image_fallback and not self.warnings:
            raise ValueError("Image fallback must remain visible as a warning")
        end = 0
        for segment in self.transcript:
            if segment.start_us < end or segment.end_us > self.source_duration_us:
                raise ValueError("transcript must be ordered and inside the source")
            end = segment.end_us
        return self


class VariantDigest(DomainModel):
    aspect: Aspect
    hook_id: HookId
    sha256: Sha256
    frame_hash: Sha256
    duration_us: Annotated[int, Field(ge=MIN_BODY_US + ENDCARD_US, le=MAX_AD_US)]
    width: PositiveInt
    height: PositiveInt
    origin_mode: ExecutionMode

    @model_validator(mode="after")
    def target_resolution(self) -> Self:
        if (self.width, self.height) != resolution(self.aspect):
            raise ValueError("rendered resolution does not match the aspect")
        return self


class RenderedVariant(VariantDigest):
    path: RelativePath
    video_codec: Literal["h264"] = "h264"
    pixel_format: Literal["yuv420p"] = "yuv420p"
    audio_codec: Literal["aac"] = "aac"

    @field_validator("path")
    @classmethod
    def mp4_only(cls, value: str) -> str:
        if PurePosixPath(value).suffix.lower() != ".mp4":
            raise ValueError("rendered video must be MP4")
        return value

    def approval_projection(self) -> VariantDigest:
        return VariantDigest.model_validate(
            self.model_dump(exclude={"path", "video_codec", "pixel_format", "audio_codec"})
        )


class ImageDigest(DomainModel):
    aspect: Aspect
    sha256: Sha256
    origin_mode: ExecutionMode


class RenderPlan(DomainModel):
    revision: PositiveInt
    media: MediaInfo
    sources: Annotated[tuple[RenderSource, ...], Field(min_length=1)]
    font_sha256: Sha256
    renderer_fingerprint: Sha256
    timeline: TimelinePlan
    crop_plans: tuple[CropPlan, CropPlan, CropPlan]
    hooks: tuple[Hook, Hook]
    enrichment: EnrichResult

    @model_validator(mode="after")
    def consistent_inputs(self) -> Self:
        if self.timeline.source_sha256 != self.media.normalized_sha256:
            raise ValueError("timeline must reference the normalized video")
        if self.timeline.source_duration_us != self.media.duration_us:
            raise ValueError("timeline duration differs from normalized media")
        videos = [source for source in self.sources if source.media_type == "video"]
        if len(videos) != 1 or videos[0].sha256 != self.media.normalized_sha256:
            raise ValueError("render requires exactly one normalized input video")
        image_hashes = {source.sha256 for source in self.sources if source.media_type == "image"}
        if any(image.sha256 not in image_hashes for image in self.enrichment.endcards):
            raise ValueError("every rendered endcard must have an allowed image source")
        if {plan.aspect for plan in self.crop_plans} != {"9:16", "4:5", "1:1"}:
            raise ValueError("render requires all three crop plans")
        for crop in self.crop_plans:
            if (crop.source_width, crop.source_height, crop.frame_count) != (
                self.media.source_width,
                self.media.source_height,
                self.media.frame_count,
            ):
                raise ValueError("crop and media geometry differ")
        if self.hooks[0].id == self.hooks[1].id:
            raise ValueError("A/B hooks must have distinct IDs")
        if self.enrichment.source_duration_us != self.media.duration_us:
            raise ValueError("enrichment and media duration differ")
        if not self.media.has_audio and self.enrichment.transcript:
            raise ValueError("a video without audio cannot have video subtitles")
        return self


class MarketingProfile(DomainModel):
    """Caller-supplied verified profile; no guessed live objective defaults."""

    objective: Cta
    optimization_goal: Cta
    billing_event: Cta
    allowed_ctas: Annotated[tuple[Cta, ...], Field(min_length=1)]
    placements: tuple[NonEmpty, ...] = ()

    @field_validator("allowed_ctas")
    @classmethod
    def unique_ctas(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("CTA allowlist must be unique")
        return value


class PublishPlan(DomainModel):
    """Settings only. Asset and approval digests belong to other contracts."""

    execution_mode: ExecutionMode
    account_id: NonEmpty
    page_id: NonEmpty
    graph_version: NonEmpty
    daily_budget_krw: PositiveInt
    currency: Literal["KRW"] = "KRW"
    country: Literal["KR"] = "KR"
    cta: Cta
    destination_url: HttpUrl | None = None
    profile: MarketingProfile
    start_at: UTCDateTime | None = None
    end_at: UTCDateTime | None = None
    campaign_status: Literal["PAUSED"] = "PAUSED"
    adset_status: Literal["PAUSED"] = "PAUSED"
    ad_status: Literal["PAUSED"] = "PAUSED"

    @model_validator(mode="after")
    def explicit_profile(self) -> Self:
        if self.cta not in self.profile.allowed_ctas:
            raise ValueError("CTA is not allowed by the selected profile")
        if self.execution_mode == "fixture":
            if not all(
                value.startswith("fixture-")
                for value in (self.account_id, self.page_id, self.graph_version)
            ):
                raise ValueError("fixture plans require explicit fixture identifiers")
        else:
            if not self.account_id.isascii() or not self.account_id.isdecimal():
                raise ValueError("live account ID must be decimal digits")
            if not self.page_id.isascii() or not self.page_id.isdecimal():
                raise ValueError("live Page ID must be decimal digits")
            parts = self.graph_version.removeprefix("v").split(".")
            if (
                not self.graph_version.startswith("v")
                or len(parts) != 2
                or not all(part.isascii() and part.isdecimal() for part in parts)
            ):
                raise ValueError("live Graph version must be explicitly versioned")
            if self.destination_url is None:
                raise ValueError("live publishing requires a destination URL")
        if self.destination_url is not None and (
            self.destination_url.username is not None or self.destination_url.password is not None
        ):
            raise ValueError("destination URL must not contain credentials")
        if self.end_at is not None and (self.start_at is None or self.end_at <= self.start_at):
            raise ValueError("end_at requires a preceding start_at")
        return self


class ApprovalSubject(DomainModel):
    """Explicit digest projection: no paths, progress, journal or remote IDs."""

    schema_version: Literal[1] = 1
    job_id: Identifier
    revision: PositiveInt
    execution_mode: ExecutionMode
    source_sha256: Sha256
    note_text: NoteText
    selected_object_id: ObjectId | None = None
    timeline: TimelinePlan
    hooks: tuple[Hook, Hook]
    primary_text: PrimaryText
    headline: Headline
    cta: Cta
    variants: Annotated[tuple[VariantDigest, ...], Field(min_length=6, max_length=6)]
    thumbnails: tuple[ImageDigest, ImageDigest, ImageDigest]
    provider_provenance: Annotated[tuple[Provenance, ...], Field(min_length=2)]
    evidence: tuple[EvidenceAssessment, ...] = ()
    claims: tuple[ClaimReview, ...] = ()
    policy_flags: tuple[Flag, ...] = ()
    warnings: tuple[NonEmpty, ...] = ()
    degraded: bool = False
    clipped: bool = False
    image_fallback: bool = False
    policy_digest: Sha256
    renderer_fingerprint: Sha256
    publish_plan: PublishPlan

    @model_validator(mode="after")
    def consistent_subject(self) -> Self:
        hook_ids = {hook.id for hook in self.hooks}
        if len(hook_ids) != 2:
            raise ValueError("approval requires two distinct hook IDs")
        expected = {(aspect, hook) for aspect in ("9:16", "4:5", "1:1") for hook in hook_ids}
        if {(variant.aspect, variant.hook_id) for variant in self.variants} != expected:
            raise ValueError("approval requires exactly six distinct aspect/hook pairs")
        if {image.aspect for image in self.thumbnails} != {"9:16", "4:5", "1:1"}:
            raise ValueError("approval thumbnails must cover all aspects")
        if self.timeline.source_sha256 != self.source_sha256:
            raise ValueError("approval timeline references another source")
        if any(variant.duration_us != self.timeline.duration_us for variant in self.variants):
            raise ValueError("approved variants must share the approved timeline duration")
        if (
            self.publish_plan.execution_mode != self.execution_mode
            or self.publish_plan.cta != self.cta
        ):
            raise ValueError("approval and publish settings disagree")
        if any(variant.origin_mode != self.execution_mode for variant in self.variants) or any(
            image.origin_mode != self.execution_mode for image in self.thumbnails
        ):
            raise ValueError("asset modes cannot cross the job execution mode")
        if any(origin.mode != self.execution_mode for origin in self.provider_provenance):
            raise ValueError("provider modes cannot cross the job execution mode")
        models = {origin.model for origin in self.provider_provenance if origin.kind == "provider"}
        if not {"muse-spark-1.3", "sam-3.1"} <= models:
            raise ValueError("approval requires Spark and SAM provenance")
        if self.image_fallback:
            if not any(
                origin.kind == "local_fallback"
                and origin.stage == "enrich"
                and origin.model == "muse-image-1.0"
                for origin in self.provider_provenance
            ):
                raise ValueError("Image fallback requires explicit fallback provenance")
        elif "muse-image-1.0" not in models:
            raise ValueError("approval requires Image provenance or an explicit fallback")
        evidence_ids = {item.id for item in self.evidence}
        if len(evidence_ids) != len(self.evidence):
            raise ValueError("duplicate evidence ID")
        if len({claim.id for claim in self.claims}) != len(self.claims):
            raise ValueError("duplicate claim ID")
        if any(not set(claim.reference_ids) <= evidence_ids for claim in self.claims):
            raise ValueError("claim references an unknown evidence ID")
        if self.image_fallback and not self.warnings:
            raise ValueError("fallback must be visible in the approval subject")
        return self

    @field_validator("variants")
    @classmethod
    def canonical_variant_order(cls, value: tuple[VariantDigest, ...]) -> tuple[VariantDigest, ...]:
        return tuple(sorted(value, key=lambda variant: (variant.aspect, variant.hook_id)))

    @field_validator("evidence")
    @classmethod
    def canonical_evidence_order(
        cls, value: tuple[EvidenceAssessment, ...]
    ) -> tuple[EvidenceAssessment, ...]:
        return tuple(sorted(value, key=lambda item: item.id))

    @field_validator("claims")
    @classmethod
    def canonical_claim_order(cls, value: tuple[ClaimReview, ...]) -> tuple[ClaimReview, ...]:
        return tuple(sorted(value, key=lambda claim: claim.id))

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )

    def content_digest(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def approval_issues(subject: ApprovalSubject) -> tuple[str, ...]:
    """Pure content checks only; authentication, files and live gates come later."""
    issues: list[str] = []
    if any(flag.severity == "block" for flag in subject.policy_flags):
        issues.append("policy_block")
    references = {item.id: item for item in subject.evidence}
    note = NoteDocument(text=subject.note_text)
    reference_validity: dict[str, bool] = {}
    for item in subject.evidence:
        reference = item.reference
        if isinstance(reference, NoteEvidence):
            matches_source = assess_evidence(item.id, reference, note=note).valid
        else:
            matches_source = (
                reference.source_digest == subject.source_sha256
                and reference.end_us <= subject.timeline.source_duration_us
            )
        reference_validity[item.id] = item.valid and matches_source
    for claim in subject.claims:
        required = claim.classification != "inference" or claim.high_risk
        # The owner said a rejected claim is not true; only rewriting the copy clears it.
        if claim.status == "rejected":
            issues.append(f"rejected_claim:{claim.id}")
        elif required and claim.status != "accepted":
            issues.append(f"unreviewed_claim:{claim.id}")
        valid_refs = [references[key] for key in claim.reference_ids if reference_validity[key]]
        if claim.classification == "explicit" and not any(
            isinstance(item.reference, NoteEvidence) for item in valid_refs
        ):
            issues.append(f"missing_note_evidence:{claim.id}")
        if claim.classification == "observation" and not any(
            isinstance(item.reference, VideoEvidence) for item in valid_refs
        ):
            issues.append(f"missing_video_evidence:{claim.id}")
        if claim.high_risk and (
            claim.classification != "explicit"
            or not any(isinstance(item.reference, NoteEvidence) for item in valid_refs)
        ):
            issues.append(f"unsupported_high_risk_claim:{claim.id}")
        if any(not reference_validity[key] for key in claim.reference_ids):
            issues.append(f"invalid_evidence:{claim.id}")
    return tuple(issues)


class ApprovalRecord(DomainModel):
    job_id: Identifier
    revision: PositiveInt
    content_digest: Sha256
    approved_at: UTCDateTime
    actor: NonEmpty
    channel: Literal["cli", "web"]

    def matches(self, subject: ApprovalSubject) -> bool:
        return (
            self.job_id == subject.job_id
            and self.revision == subject.revision
            and self.content_digest == subject.content_digest()
            and not approval_issues(subject)
        )


class PublishOperation(DomainModel):
    job_id: Identifier
    revision: PositiveInt
    execution_mode: ExecutionMode
    resource_kind: Literal["video", "image", "creative", "campaign", "adset", "ad"]
    hook_id: HookId | None = None
    request_fingerprint: Sha256
    phase: Literal["PREPARED", "CONFIRMED", "FAILED", "UNKNOWN"]
    remote_id: NonEmpty | None = None
    error: ErrorDetail | None = None
    abandoned: bool = False
    resolution_actor: NonEmpty | None = None

    @model_validator(mode="after")
    def journal_consistency(self) -> Self:
        if self.resource_kind in {"video", "creative", "ad"} and self.hook_id is None:
            raise ValueError("per-hook resource requires a hook ID")
        if self.resource_kind in {"campaign", "adset"} and self.hook_id is not None:
            raise ValueError("shared resource must not have a hook ID")
        if (self.phase == "CONFIRMED") != (self.remote_id is not None):
            raise ValueError("only CONFIRMED operations contain a remote ID")
        if self.phase in {"FAILED", "UNKNOWN"} and self.error is None:
            raise ValueError("failed or unknown operations require an error")
        if self.phase in {"PREPARED", "CONFIRMED"} and self.error is not None:
            raise ValueError("prepared or confirmed operation cannot carry a failure")
        if self.abandoned and (
            self.phase not in {"PREPARED", "UNKNOWN"} or self.resolution_actor is None
        ):
            raise ValueError("abandon requires an unresolved operation and a human actor")
        return self

    @property
    def operation_key(self) -> str:
        hook = self.hook_id if self.hook_id is not None else "_shared"
        return f"{self.job_id}.{self.revision}.{self.execution_mode}.{self.resource_kind}.{hook}"


class PublishedAd(DomainModel):
    hook_id: HookId
    video_id: NonEmpty
    creative_id: NonEmpty
    ad_id: NonEmpty
    configured_status: Literal["PAUSED"]
    effective_status: Cta


class PublishResult(DomainModel):
    job_id: Identifier
    revision: PositiveInt
    execution_mode: ExecutionMode
    campaign_id: NonEmpty
    adset_id: NonEmpty
    campaign_status: Literal["PAUSED"]
    adset_status: Literal["PAUSED"]
    ads: tuple[PublishedAd, PublishedAd]
    thumbnail_hashes: Annotated[tuple[NonEmpty, ...], Field(min_length=1)]
    checked_at: UTCDateTime

    @model_validator(mode="after")
    def two_distinct_ads(self) -> Self:
        for field in ("hook_id", "video_id", "creative_id", "ad_id"):
            if getattr(self.ads[0], field) == getattr(self.ads[1], field):
                raise ValueError(f"the two ads must have distinct {field} values")
        return self


class RemoteFileAttempt(DomainModel):
    attempt_id: Identifier
    source_sha256: Sha256
    phase: Literal["PREPARED", "CONFIRMED", "UNKNOWN", "DELETED", "CLEANUP_REQUIRED"]
    remote_id: NonEmpty | None = None
    error: ErrorDetail | None = None
    abandoned_by: NonEmpty | None = None
    new_attempt_authorized: bool = False

    @model_validator(mode="after")
    def cleanup_state(self) -> Self:
        if self.phase in {"CONFIRMED", "DELETED"} and self.remote_id is None:
            raise ValueError("confirmed or deleted file requires a known remote ID")
        if self.phase in {"PREPARED", "UNKNOWN"} and self.remote_id is not None:
            raise ValueError("unconfirmed upload must not claim a remote ID")
        if self.phase in {"UNKNOWN", "CLEANUP_REQUIRED"} and self.error is None:
            raise ValueError("unresolved file cleanup requires an error")
        if self.new_attempt_authorized and (
            self.abandoned_by is None or self.phase not in {"UNKNOWN", "CLEANUP_REQUIRED"}
        ):
            raise ValueError("new upload attempt needs a recorded human abandonment")
        return self


class JobManifest(DomainModel):
    schema_version: Literal[1] = 1
    job_id: Identifier
    revision: PositiveInt
    manifest_seq: PositiveInt
    execution_mode: ExecutionMode
    state: JobState
    last_success_state: JobState
    run_state: RunState
    active_run_id: Identifier | None = None
    note_status: Literal["AUDIO_PENDING", "REVIEW_REQUIRED", "CONFIRMED"]
    manifest_ref: ArtifactRef
    approval_ref: ArtifactRef | None = None
    failed_stage: Stage | None = None
    pending_stage: Stage | None = None
    error: ErrorDetail | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @model_validator(mode="after")
    def coherent_head(self) -> Self:
        if self.last_success_state == "FAILED":
            raise ValueError("last successful state cannot be FAILED")
        ordered_states: tuple[JobState, ...] = (
            "CREATED",
            "UNDERSTOOD",
            "TRACKED",
            "ENRICHED",
            "RENDERED",
            "AWAITING_APPROVAL",
            "APPROVED",
            "PUBLISHED_PAUSED",
        )
        if self.state != "FAILED" and (
            ordered_states.index(self.last_success_state) > ordered_states.index(self.state)
        ):
            raise ValueError("last successful state cannot be ahead of the current state")
        running = self.run_state in {"RUNNING", "CANCEL_REQUESTED"}
        if running != (self.active_run_id is not None):
            raise ValueError("running jobs require an owner; idle/interrupted jobs must clear it")
        if running and self.pending_stage is None:
            raise ValueError("running job must identify its pending stage")
        if self.state == "FAILED" and (
            self.failed_stage is None or self.error is None or self.pending_stage is None
        ):
            raise ValueError("FAILED requires an error, failed stage and resume stage")
        if (self.failed_stage is None) != (self.error is None):
            raise ValueError("failure metadata must retain both stage and error")
        if self.error is not None and self.error.stage != self.failed_stage:
            raise ValueError("error stage and failed stage disagree")
        if self.state in {"APPROVED", "PUBLISHED_PAUSED"} and self.approval_ref is None:
            raise ValueError("approved or published state requires an approval reference")
        if self.approval_ref is not None and self.last_success_state not in {
            "APPROVED",
            "PUBLISHED_PAUSED",
        }:
            raise ValueError("approval reference cannot survive content invalidation")
        effective_state = self.last_success_state if self.state == "FAILED" else self.state
        if effective_state != "CREATED" and self.note_status != "CONFIRMED":
            raise ValueError("understanding requires a confirmed note")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at precedes created_at")
        return self
