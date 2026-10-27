import subprocess
from pathlib import Path

import pytest

from adloom.adapters.mock_providers import MockImage, MockTracking, MockVoice
from adloom.jobs import Snapshot
from adloom.schemas import Brief, Provenance, Understanding
from adloom.stages.assemble import assemble
from adloom.stages.enrich import enrich
from adloom.stages.input import normalize
from adloom.stages.track import track


@pytest.fixture(scope="session")
def rendered_case(tmp_path_factory):
    root = tmp_path_factory.mktemp("rendered")
    source = root / "source.mp4"
    subprocess.run(["bash", "tests/fixtures/make_sample.sh", str(source)], check=True)
    normalized = root / "input/normalized.mp4"
    media = normalize(source, normalized)
    fixture = Path("tests/fixtures/understanding/19eb07d4553ab7aa988d4b7acd932cb694633fded3c49b3ff664aa32e13d5a48.json")
    understanding = Understanding.model_validate_json(fixture.read_bytes())
    tracked, crops = track(normalized, understanding.sam_prompt, MockTracking())
    enriched = enrich(normalized, media, understanding, root, MockImage(root), MockVoice(root))
    snapshot = Snapshot(brief=Brief(video_path="input/normalized.mp4", note_text="합성 샘플",
                                    region="서울", daily_budget_krw=10000),
                        media=media, understanding=understanding, track=tracked,
                        crops=crops, enrichment=enriched,
                        provenance=tuple(Provenance(mode="fixture", stage=stage, kind="provider", model=model, capture_id="test-fixture")
                                         for stage, model in (("understand", "muse-spark-1.3"), ("track", "sam-3.1"), ("enrich", "muse-image-1.0"))))
    return root, assemble(root, snapshot, 1)
