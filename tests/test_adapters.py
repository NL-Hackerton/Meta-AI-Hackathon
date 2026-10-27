import importlib

import pytest

from adloom.config import AdLoomError, load_config


def test_factory_refuses_explicit_live(monkeypatch, tmp_path):
    base = importlib.import_module("adloom.adapters.base")
    monkeypatch.setenv("ADLOOM_LIVE", "1")
    with pytest.raises(AdLoomError, match="E_API_AUTH"):
        base.get_adapters(job_dir=tmp_path)


def test_marketing_mock_enforces_paused_and_uses_operation_identity(tmp_path):
    base = importlib.import_module("adloom.adapters.base")
    adapters = base.get_adapters(load_config({}), tmp_path)
    publisher = adapters.marketing
    with pytest.raises(AdLoomError):
        publisher.create("campaign", {"status": "ACTIVE"}, "bad")
    first = publisher.create("campaign", {"status": "PAUSED"}, "one")
    assert first == publisher.create("campaign", {"status": "PAUSED"}, "one")
    assert first != publisher.create("campaign", {"status": "PAUSED"}, "two")


def test_unknown_fixture_does_not_claim_video_understanding(tmp_path):
    base = importlib.import_module("adloom.adapters.base")
    video = tmp_path / "unknown.mp4"
    video.write_bytes(b"unknown")
    adapters = base.get_adapters(load_config({}), tmp_path)
    with pytest.raises(AdLoomError, match="E_API_SCHEMA"):
        adapters.spark.understand(video, "컵", "ko")
