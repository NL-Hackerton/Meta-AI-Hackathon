from pathlib import Path

from adloom.config import FONT_PATH, AdLoomError
from adloom.jobs import Snapshot, file_hash
from adloom.render import plan_timeline, render, renderer_fingerprint
from adloom.schemas import RenderPlan, RenderSource


def assemble(root: Path, snapshot: Snapshot, revision: int) -> Snapshot:
    understanding, enrichment = snapshot.understanding, snapshot.enrichment
    if understanding is None or enrichment is None or len(snapshot.crops) != 3:
        raise AdLoomError("E_STATE_CONFLICT", "assemble", "Understanding, crops and enrichment required")
    plan = RenderPlan(
        revision=revision, media=snapshot.media,
        sources=(RenderSource(path=snapshot.brief.video_path, sha256=snapshot.media.normalized_sha256,
                              source_type="input_video", media_type="video"),
                 *(RenderSource(path=i.path, sha256=i.sha256, source_type="muse_image", media_type="image")
                   for i in enrichment.endcards)),
        font_sha256=file_hash(FONT_PATH), renderer_fingerprint=renderer_fingerprint(),
        timeline=plan_timeline(snapshot.media, understanding.key_moments),
        crop_plans=(snapshot.crops[0], snapshot.crops[1], snapshot.crops[2]),
        hooks=(understanding.hook_candidates[0], understanding.hook_candidates[1]), enrichment=enrichment,
    )
    return snapshot.model_copy(update={"render_plan": plan, "variants": render(root, plan)})
