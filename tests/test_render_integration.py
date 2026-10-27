import io
import subprocess
from pathlib import Path

from PIL import Image

from adloom.adapters.mock_providers import MockImage, MockTracking, MockVoice
from adloom.jobs import Snapshot
from adloom.schemas import Brief, Understanding
from adloom.stages.assemble import assemble
from adloom.stages.enrich import enrich
from adloom.stages.input import normalize
from adloom.stages.track import track


def test_six_encodes_are_deterministic_and_hook_disappears(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(["bash", "tests/fixtures/make_sample.sh", str(source)], check=True)
    normalized = tmp_path / "input/normalized.mp4"
    media = normalize(source, normalized)
    fixture = Path(
        "tests/fixtures/understanding/19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json"
    )
    understanding = Understanding.model_validate_json(fixture.read_bytes())
    tracked, crops = track(normalized, understanding.sam_prompt, MockTracking())
    enriched = enrich(
        normalized, media, understanding, tmp_path, MockImage(tmp_path), MockVoice(tmp_path)
    )
    snapshot = Snapshot(
        brief=Brief(
            video_path="input/normalized.mp4",
            note_text="합성 샘플",
            region="서울",
            daily_budget_krw=10000,
        ),
        media=media,
        understanding=understanding,
        track=tracked,
        crops=crops,
        enrichment=enriched,
    )
    first = assemble(tmp_path, snapshot, 1)
    second = assemble(tmp_path, snapshot, 1)
    assert [(v.aspect, v.hook_id) for v in second.variants] == [
        (a, h) for a in ("9:16", "4:5", "1:1") for h in ("a", "b")
    ]
    assert [v.frame_hash for v in first.variants] == [v.frame_hash for v in second.variants]
    assert all(v.duration_us == 8000000 for v in second.variants)
    video = tmp_path / second.variants[0].path
    counts = []
    for time in (2, 4):
        raw = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(time),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "png",
                "-",
            ]
        )
        with Image.open(io.BytesIO(raw)) as image:
            pixels = image.convert("RGB").crop((0, 200, 1080, 650))
            counts.append(sum(min(pixel) > 230 for pixel in pixels.get_flattened_data()))
    assert counts[0] > 100 and counts[1] == 0
