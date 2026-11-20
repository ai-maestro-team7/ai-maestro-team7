"""공공기관 직원 평균보수를 공고에 잇기 (B-D11): 카드, 상세, 연봉 조건, 채팅 도구.

데모 기관 이름에 가짜 평균보수를 넣어 본다. 실제 값은 수집 배치가 알리오에서 채운다.
"""

import pytest

from opportunity.api.agent_handler import agent_feed
from opportunity.core import org_pay, posting_detail, ranking
from opportunity.models.posting import OrgPay, OrgPayYear
from opportunity.seeds import demo_world as w

FINANCE = "alio-DEMO0001"      # 가상금융공사, 공고에 급여 없음
HOUSING = "alio-DEMO0002"      # 가상주택금융공사, 공고 급여 연 3,600만 원
OCEAN = "alio-DEMO0003"        # 가상해양공단, 공고에 급여 없음, 평균보수 없음


def pay(name, average, org_id="C9001"):
    return OrgPay(org_id=org_id, name=name, org_type="공기업(준시장형)", latest_year=2025, latest_average=average,
                  years=[OrgPayYear(year=2024, average=average - 300), OrgPayYear(year=2025, average=average),
                         OrgPayYear(year=2026, average=average - 500, budget=True)],
                  tenure_months=132, source="알리오 경영공시 · 직원 평균보수 (일반정규직)", as_of="2025-12-31",
                  source_url="https://www.alio.go.kr/item/itemReportTerm.do?apbaId=C9001&reportFormRootNo=20601")


@pytest.fixture
def paid(deps):
    deps.catalog.put_org_pay(pay("가상금융공사", 9118))
    deps.catalog.put_org_pay(pay("가상주택금융공사", 8000, org_id="C9002"))
    return deps


def feed(deps, as_of, **kwargs):
    return {c.job_posting_id: c for c in ranking.search_postings(deps, "demo3", as_of=as_of, limit=100, **kwargs).items}


def test_name_key_ignores_legal_marks_and_spaces():
    assert org_pay.name_key("(재)우체국 물류지원단") == org_pay.name_key("우체국물류지원단")
    assert org_pay.name_key("한국남부발전(주)") == org_pay.name_key("한국남부발전 주식회사")


def test_card_carries_org_pay_without_changing_posting_salary(paid, as_of):
    cards = feed(paid, as_of)
    finance = cards[FINANCE]
    assert (finance.org_pay.average, finance.org_pay.year) == (9118, 2025)
    assert not finance.salary.disclosed  # 공고 급여는 그대로 비어 있다
    assert cards[HOUSING].org_pay.average == 8000 and cards[HOUSING].salary.min == 3600
    assert w.BUSAN_DATA not in cards or cards[w.BUSAN_DATA].org_pay is None  # 민간 회사는 없다


def test_min_salary_uses_org_average_only_when_posting_has_no_salary(paid, as_of):
    kept = feed(paid, as_of, min_salary=9000)
    assert FINANCE in kept               # 공고 급여 없음 → 기관 평균 9,118만 원으로 본다
    assert HOUSING not in kept           # 공고 급여 3,600만 원이 있으면 그 값으로 본다 (기관 평균 8,000은 쓰지 않는다)
    assert OCEAN in kept                 # 급여도 평균보수도 없으면 남긴다 (미확인 ≠ 미달)
    dropped = feed(paid, as_of, min_salary=9500)
    assert FINANCE not in dropped and OCEAN in dropped


def test_detail_has_years(paid, as_of):
    detail = posting_detail.get_posting(paid, "demo3", FINANCE, as_of=as_of)
    assert detail.org_pay.latest_average == 9118
    assert [(y.year, y.budget) for y in detail.org_pay.years] == [(2024, False), (2025, False), (2026, True)]
    assert posting_detail.get_posting(paid, "demo3", OCEAN, as_of=as_of).org_pay is None


def test_agent_feed_says_it_is_an_org_average(paid, as_of):
    items = {i.job_posting_id: i for i in agent_feed(paid, "demo3", limit=50).items}
    assert items[FINANCE].salary == "공고에 없음"
    assert items[FINANCE].org_pay == "기관 직원 평균 연 9,118만 원 (2025년 결산 · 알리오 경영공시, 신입 초봉 아님)"
    assert items[OCEAN].org_pay is None


def test_public_list_shows_org_average(paid, as_of):
    from opportunity.core.public_postings import list_public_postings

    items = {c.job_posting_id: c for c in list_public_postings(paid, limit=50, as_of=as_of).items}
    assert items[FINANCE].org_pay.average == 9118 and not items[FINANCE].salary.disclosed
    assert items[OCEAN].org_pay is None


def test_label_follows_source_and_year_note():
    assert org_pay.label(5301, 2025, "클린아이 경영공시 · 지방출자출연기관 직원평균임금 (행정안전부)", "") == (
        "기관 직원 평균 연 5,301만 원 (2025년 · 클린아이 경영공시, 신입 초봉 아님)")
    assert org_pay.label(9118, 2025, "알리오 경영공시 · 직원 평균보수 (일반정규직)") == (
        "기관 직원 평균 연 9,118만 원 (2025년 결산 · 알리오 경영공시, 신입 초봉 아님)")
