import importlib


def test_guarantee_is_blocked_and_suggestion_is_rechecked():
    policy = importlib.import_module("adloom.policy")
    flags = policy.check({"primary_text": "100% 보장하는 서비스"})
    assert len(flags) == 1
    assert flags[0].severity == "block"
    assert flags[0].field == "primary_text"
    assert not policy.check({"primary_text": flags[0].rewrite})
    assert not policy.check({"headline": "제품을 확인하세요"})
