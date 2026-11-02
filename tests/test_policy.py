import importlib
import re

import pytest

policy = importlib.import_module("adloom.policy")

# rule id -> (texts the rule must flag, nearby texts no rule may flag)
CASES: dict[str, tuple[list[str], list[str]]] = {
    "personal_attribute_en": (
        [
            "Are you diabetic? Try our low-sugar cake",
            "Do you have diabetes?",
            "Are you 18 years old?",
            "Depression getting you down? Get help now.",
            "Are you bankrupt? Check out our services.",
            "Questioning your gender identity?",
        ],
        [
            "Are you ready for summer?",
            "Do you have five minutes?",
            "New diabetes treatment available",
            "Are you a coffee lover?",
            "Meet seniors at our café",
        ],
    ),
    "personal_attribute_ko": (
        [
            "당뇨가 있으신가요? 저당 케이크",
            "탈모로 고민하시나요?",
            "임신 중이신가요?",
            "혹시 우울증이신가요?",
            "당신의 탈모, 이제 그만",
            "빚 때문에 힘드신가요?",
        ],
        [
            "당뇨 환자를 위한 저당 케이크",
            "임신 축하 케이크 주문 받아요",
            "예약 있으신가요?",
            "게이밍 의자 고민이신가요?",
        ],
    ),
    "health_cure_claim_en": (
        ["This tea cures diabetes", "A cure for cancer", "No side effects at all"],
        ["Soothes dry skin", "Helps manage diabetes symptoms", "Side effects may vary"],
    ),
    "health_cure_claim_ko": (
        ["관절염 완치", "부작용 없음", "부작용이 없는 다이어트", "당뇨를 고쳐 드려요"],
        [
            "피로 회복에 도움",
            "부작용은 전문가와 상담하세요",
            "암호 없이 접속",
            "당뇨 환자용 저당 빵",
        ],
    ),
    "weight_loss_timeframe_en": (
        ["Lose 10 kg in 2 weeks", "Drop 5 lbs in 7 days", "shed 3 pounds in a week"],
        ["Ships 2 kg of beans in 3 days", "Our 5 kg flour bag"],
    ),
    "weight_loss_timeframe_ko": (
        ["2주 만에 5kg 감량", "한 달 -10kg", "일주일에 3키로 빠져요"],
        ["3일 안에 1kg 원두 배송", "3일 만에 완판", "5kg 쌀 한 포대"],
    ),
    "negative_self_image_en": (
        ["Ugly belly fat? Not anymore", "Hate your thighs?", "Tired of being fat?"],
        ["Belly-warming soup", "Feel good in your skin", "Fat-free yogurt"],
    ),
    "negative_self_image_ko": (
        ["뱃살 고민 끝!", "못생긴 피부 탈출", "팔뚝살 때문에 스트레스"],
        ["뚱카롱 맛집", "통통한 새우", "삼겹살 맛집"],
    ),
    "before_after_en": (
        ["See the before and after", "Before & after photos", "before/after"],
        ["Before and after school care", "Before you order, call us"],
    ),
    "before_after_ko": (
        ["비포 애프터 공개", "시술 전후 비교", "사용 전 후"],
        ["식사 전후로 드세요", "주문 전 확인 후 결제", "전후좌우"],
    ),
    "guaranteed_results_en": (
        ["100% guaranteed", "Guaranteed results in days", "Works every time", "100% effective"],
        ["Money-back guarantee", "100% organic cotton", "Satisfaction guarantee with refund"],
    ),
    "guaranteed_results_ko": (
        ["100% 보장하는 서비스", "무조건 효과", "효과를 보장합니다", "합격 보장"],
        ["100% 환불 보장", "100% 국내산", "무조건 맛있어요", "품질 보증서 제공"],
    ),
    "income_promise_en": (
        [
            "Guaranteed returns every month",
            "Risk-free investment",
            "Earn $500 a day from home",
            "Get rich quick",
            "Double your money",
        ],
        ["Risk-free trial for 30 days", "We make 200 cookies a day", "Earn 2x points per visit"],
    ),
    "income_promise_ko": (
        ["원금 보장", "수익률 보장 상품", "월 500만원 수익", "일확천금의 기회", "대출 승인 보장"],
        ["월 30만원 이상 구매 시 무료배송", "수익금 일부 기부", "월요일 휴무"],
    ),
    "unproven_superlative_en": (
        [
            "The best coffee in town",
            "#1 bakery in Seoul",
            "No. 1 choice",
            "World's first edible cup",
        ],
        ["Best before 2026-12-01", "Best regards", "We do our best every day", "Room 1 is open"],
    ),
    "unproven_superlative_ko": (
        ["동네 최고의 커피", "커피가 최고예요", "판매 1위 빵집", "국내 최초 디저트", "넘버원 맛집"],
        ["최고급 원두 사용", "최고기온 30도", "11위 기록", "1등급 한우", "1층 매장"],
    ),
    "urgency_scarcity_en": (
        ["Today only: 20% off", "Only 3 left!", "Hurry, ends tonight", "Act now"],
        ["Open today until 9", "No hurry, take your time", "Available now"],
    ),
    "urgency_scarcity_ko": (
        ["오늘만 20% 할인", "마감 임박!", "단 5개 남았어요", "마지막 기회"],
        ["오늘도 영업합니다", "예약 마감 시간은 9시", "5개 묶음 판매"],
    ),
    "misleading_price_en": (
        ["Totally free!", "Free forever", "Lowest price guaranteed", "The cheapest in town"],
        ["Completely free of sugar", "100% gluten free", "Free delivery over $30"],
    ),
    "misleading_price_ko": (
        ["완전 무료!", "평생 무료 이용", "최저가 보장", "역대 최저가"],
        ["3만원 이상 무료배송", "무료 시식 행사(재고 소진 시 종료)", "최저 기온"],
    ),
}


def test_every_rule_has_cases_and_a_meta_source():
    assert {rule.id for rule in policy.RULES} == set(CASES)
    for rule in policy.RULES:
        assert rule.policy_url.startswith(
            ("https://transparency.meta.com/", "https://www.facebook.com/business/")
        )


@pytest.mark.parametrize(
    ("rule_id", "text"), [(rule_id, text) for rule_id, (hits, _) in CASES.items() for text in hits]
)
def test_rule_flags_positive_and_its_rewrite_clears_it(rule_id, text):
    flags = [flag for flag in policy.check({"primary_text": text}) if flag.rule_id == rule_id]
    assert len(flags) == 1
    rule = next(rule for rule in policy.RULES if rule.id == rule_id)
    assert flags[0].severity == rule.severity
    assert flags[0].original == text
    assert rule.replacement in flags[0].rewrite
    assert rule_id not in {flag.rule_id for flag in policy.check({"headline": flags[0].rewrite})}


@pytest.mark.parametrize(
    "text", [text for _, misses in CASES.values() for text in misses], ids=lambda text: text
)
def test_negative_is_not_flagged_by_any_rule(text):
    assert policy.check({"primary_text": text}) == ()


def test_replacements_are_concrete_and_flag_nothing():
    for rule in policy.RULES:
        assert rule.replacement.strip()
        assert not re.search(r"[{}<>]|\\\d", rule.replacement)
        assert policy.check({"primary_text": rule.replacement}) == ()


def test_guarantee_is_blocked_and_suggestion_is_rechecked():
    flags = policy.check({"primary_text": "100% 보장하는 서비스"})
    assert len(flags) == 1
    assert flags[0].severity == "block"
    assert flags[0].field == "primary_text"
    assert flags[0].rewrite == "정성을 다하는 서비스"
    assert not policy.check({"primary_text": flags[0].rewrite})
    assert not policy.check({"headline": "제품을 확인하세요"})


def test_field_scope_and_uneditable_subtitles_only_warn():
    fields = {"hook:a": "Are you diabetic?", "subtitle:0": "Are you diabetic?", "cta": "완치"}
    flags = {flag.field: flag for flag in policy.check(fields)}
    assert flags["hook:a"].severity == "block"
    assert flags["subtitle:0"].severity == "warn"
    assert "cta" not in flags


def test_warn_rules_do_not_block():
    flags = policy.check({"headline": "오늘만 동네 최고의 커피"})
    assert {flag.rule_id for flag in flags} == {"urgency_scarcity_ko", "unproven_superlative_ko"}
    assert {flag.severity for flag in flags} == {"warn"}
