import importlib

import pytest


def test_standard_model_and_fixture_default():
    config = importlib.import_module("adloom.config")
    settings = config.load_config({})
    assert settings.mode == "fixture"
    assert settings.spark_model == "muse-spark-1.3"
    with pytest.raises(config.AdLoomError, match="E_INPUT_INVALID"):
        config.load_config({"ADLOOM_SPARK_MODEL": "muse-spark-1.3-contributor"})


def test_live_never_silently_becomes_mock():
    config = importlib.import_module("adloom.config")
    with pytest.raises(config.AdLoomError, match="E_API_AUTH"):
        config.load_config({"ADLOOM_LIVE": "1"})
    with pytest.raises(config.AdLoomError, match="E_INPUT_INVALID"):
        config.load_config({"ADLOOM_LIVE": "true"})
