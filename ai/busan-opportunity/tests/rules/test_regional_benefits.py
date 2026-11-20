"""지역 조건을 사용자의 학교 소재지·거주지와 견주기 (`core.facts.regional_talent_view`)와 피드의 지역 혜택 거르기.

demo3: 부산 금정구(26410) 거주, 부산 소재 학교 졸업 예정.
"""

from opportunity.core import copy_rules, facts, ranking
from opportunity.models.enums import RegionalBenefitKind as K
from opportunity.models.enums import RegionalTalentStatus as S
from opportunity.models.posting import RegionalCondition, RegionalTalent
from opportunity.seeds import demo_world as w


def _with(deps, pid, *conditions, basis="공고문 근거"):
    """민간 공고(BUSAN_DATA)에 지역 조건을 붙여 넣는다. 색인도 함께 맞춘다."""
    latest = deps.catalog.get_latest(pid).model_copy(update={"regional_talent": RegionalTalent(
        status=S.LIKELY, basis=basis, conditions=[RegionalCondition(kind=k, sido=s, sigungu=g) for k, s, g in conditions])})
    deps.catalog.put_latest(latest)
    deps.catalog.put_regional_index(latest)
    return latest


def _profile(deps, user="demo3", **update):
    deps.users.profiles[user] = deps.users.get_basic_profile(user).model_copy(update=update)
    return deps.users.profiles[user]


def view(deps, latest, user="demo3"):
    return facts.regional_talent_view(deps.config, deps.users.get_basic_profile(user), latest)


# ---------------------------------------------------------------- 학교 소재지
def test_non_capital_matches_busan_school_not_seoul(deps):
    latest = _with(deps, w.BUSAN_DATA, (K.NON_CAPITAL, None, None))
    likely = view(deps, latest)
    assert likely.status == S.LIKELY
    assert likely.message == "부산 소재 학교 졸업 예정이라 비수도권 지역인재 우대 대상일 수 있어요 · 공고문 확인"
    _profile(deps, university_region="11")
    assert view(deps, latest).status == S.NOT_APPLICABLE
    _profile(deps, university_region=None)
    assert view(deps, latest).status == S.CHECK_NEEDED


def test_school_region_and_merged_sido(deps):
    daegu = _with(deps, w.BUSAN_DATA, (K.SCHOOL, "27", None), (K.SCHOOL, "47", None))
    assert view(deps, daegu).status == S.NOT_APPLICABLE  # 부산 학교는 대구·경북 이전지역인재가 아니다
    _profile(deps, university_region="47")
    assert view(deps, daegu).status == S.LIKELY
    merged = _with(deps, w.BUSAN_DATA, (K.SCHOOL, "12", None))  # 전남광주통합특별시
    _profile(deps, university_region="29")  # 옛 광주 코드
    assert view(deps, merged).status == S.LIKELY


# ---------------------------------------------------------------- 거주지
def test_residence_sigungu_needs_matching_gu(deps):
    gijang = _with(deps, w.BUSAN_DATA, (K.RESIDENCE, "26", "기장군"))
    assert view(deps, gijang).status == S.NOT_APPLICABLE  # 금정구 거주
    _profile(deps, residence_sigungu="26710")
    likely = view(deps, gijang)
    assert likely.status == S.LIKELY
    assert likely.message == "부산 기장군에 살고 있어 이 공고의 지역 조건에 맞을 수 있어요 · 공고문 확인"


def test_region_limit_matches_school_or_residence(deps):
    limit = _with(deps, w.BUSAN_DATA, (K.SCHOOL_OR_RESIDENCE, "26", None))
    assert view(deps, limit).message == copy_rules.REGIONAL_LIMIT_SCHOOL.format(school="부산", status="졸업 예정")
    _profile(deps, university_region="11")
    assert view(deps, limit).message.startswith("부산 금정구에 살고 있어")
    _profile(deps, residence_sido="11", residence_sigungu=None)
    assert view(deps, limit).status == S.NOT_APPLICABLE


def test_unknown_region_is_check_needed(deps):
    latest = _with(deps, w.BUSAN_DATA, (K.UNKNOWN, None, None))
    result = view(deps, latest)
    assert result.status == S.CHECK_NEEDED and result.message == copy_rules.REGIONAL_TALENT_CHECK_NOTICE


def test_messages_have_no_forbidden_copy(deps):
    for cond in ((K.NON_CAPITAL, None, None), (K.SCHOOL, "26", None), (K.RESIDENCE, "26", None),
                 (K.SCHOOL_OR_RESIDENCE, "26", None), (K.UNKNOWN, None, None)):
        message = view(deps, _with(deps, w.BUSAN_DATA, cond)).message or ""
        assert message.endswith("공고문에서 확인해 주세요") or message.endswith("공고문 확인")
        assert not copy_rules.find_forbidden(message)


# ---------------------------------------------------------------- 피드 거르기
class NoVectors:
    """벡터 질의가 아무것도 돌려주지 않는 상황 (희망 직무와 먼 공고만 지역 조건이 맞을 때)."""

    def __init__(self, inner):
        self.inner = inner

    def query(self, vector, *, top_k, filter=None):
        return []

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_filter_finds_postings_outside_vector_candidates(deps, as_of):
    _with(deps, w.SEOUL_DATA, (K.NON_CAPITAL, None, None))
    deps.vectors = NoVectors(deps.vectors)
    only = ranking.search_postings(deps, "demo3", as_of=as_of, regional_talent=True, limit=100)
    found = {c.job_posting_id: c for c in only.items}
    assert w.SEOUL_DATA in found and w.BUSAN_FINANCE_PUBLIC in found
    assert all(c.regional_talent == S.LIKELY for c in only.items)
    assert facts.FACT_REGIONAL_TALENT_CARD in found[w.SEOUL_DATA].facts


def test_filter_keeps_only_postings_the_user_meets(deps, as_of):
    _with(deps, w.SEOUL_DATA, (K.SCHOOL, "27", None))  # 대구 학교만
    _with(deps, w.BUSAN_DATA, (K.UNKNOWN, None, None))  # 어느 지역인지 모름
    only = ranking.search_postings(deps, "demo3", as_of=as_of, regional_talent=True, limit=100)
    ids = [c.job_posting_id for c in only.items]
    assert w.SEOUL_DATA not in ids and w.BUSAN_DATA not in ids
    assert w.BUSAN_ADMIN_PUBLIC not in ids  # 이전기관인데 공고문에 조건이 없으면 확인 필요라 거르기에서는 뺀다
