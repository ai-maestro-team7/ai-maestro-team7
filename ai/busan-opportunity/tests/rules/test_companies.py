"""부산 기업 둘러보기 (`core/companies.py`, DECISIONS.md B-D01).

청끌기업은 회사 정보로만 보여 준다. 채용 여부·직무·급여를 만들지 않고, 출처 없는 배지는 쓰지 않는다.
"""

import pytest

from opportunity.core import companies, copy_rules
from opportunity.models.enums import BadgeType, CheonggeulType
from opportunity.models.errors import OppError
from opportunity.models.posting import Badge, CompanyRecord
from opportunity.models.profile import BasicProfile, DesiredJob
from opportunity.seeds import demo_world as w

CG_SRC = {"source": "부산광역시 2026년 청끌기업 선정 (테스트)", "as_of": "2026-03-26"}
CG_LABEL = {CheonggeulType.SALARY: "청끌기업 · 급여", CheonggeulType.WELFARE: "청끌기업 · 복지",
            CheonggeulType.WORK_LIFE: "청끌기업 · 워라밸", CheonggeulType.FUTURE: "청끌기업 · 미래"}
REC_SRC = {"source": "부산광역시 (테스트)", "as_of": "2026-11-20"}


def cg(kind: CheonggeulType, *, sourced: bool = True) -> Badge:
    extra = CG_SRC if sourced else {}
    return Badge(type=BadgeType.CHEONGKKEUL, label=CG_LABEL[kind], cheonggeul_type=kind, **extra)


def company(cid, name, *badges, sido="26", industry=None, product=None, district="해운대구", size=None):
    return CompanyRecord(company_id=cid, name=name, sido=sido, industry=industry, main_product=product,
                         district=district, size=size, highlights=list(badges), **REC_SRC)


@pytest.fixture
def world(deps):
    """데모 회사는 비우고 이 파일의 회사만 둔다."""
    deps.catalog.companies.clear()
    rows = [
        company("t-01", "가나소프트", cg(CheonggeulType.FUTURE), industry="응용 소프트웨어 개발 및 공급업",
                product="데이터 분석 플랫폼", size="상시근로자 40명"),
        company("t-02", "다라정밀", cg(CheonggeulType.SALARY), industry="기계 부품 제조업", product="선박용 밸브",
                district="강서구"),
        company("t-03", "마바복지", cg(CheonggeulType.WELFARE), industry="식료품 제조업", product="어묵"),
        company("t-04", "사아세무", cg(CheonggeulType.WORK_LIFE), industry="회계 및 세무 관련 서비스업",
                product="기장 대행", district="부산진구"),
        company("t-05", "자차통계", cg(CheonggeulType.SALARY), industry="시장 조사 및 여론 조사업",
                product="통계 조사"),
        # 빠져야 하는 회사
        company("t-90", "출처없음", cg(CheonggeulType.SALARY, sourced=False), industry="데이터 분석업"),
        company("t-91", "강소만", Badge(type=BadgeType.GANGSO, label="청년일자리강소기업", **REC_SRC),
                industry="데이터 분석업"),
        company("t-92", "서울데이터", cg(CheonggeulType.SALARY), sido="11", industry="데이터 분석업"),
    ]
    for row in rows:
        deps.catalog.put_company(row)
    return deps


def set_profile(deps, user_id, **kwargs):
    deps.users.profiles[user_id] = BasicProfile(**kwargs)


def ids(resp):
    return [c.company_id for c in resp.items]


def run(deps, user_id="nobody", **kwargs):
    return companies.list_busan_companies(deps, user_id, as_of=w.DEMO_AS_OF, **kwargs)


def test_only_sourced_cheonggeul_in_busan(world):
    resp = run(world)
    assert set(ids(resp)) == {"t-01", "t-02", "t-03", "t-04", "t-05"}
    for card in resp.items:
        assert card.badges and all(b.source and b.as_of for b in card.badges)
        assert any(b.type == BadgeType.CHEONGKKEUL for b in card.badges)


def test_unsourced_badge_only_company_is_dropped(world):
    assert "t-90" not in ids(run(world))


def test_non_busan_company_is_dropped(world):
    assert "t-92" not in ids(run(world))


def test_unsourced_badge_is_removed_from_card(world):
    world.catalog.put_company(company("t-06", "섞인배지", cg(CheonggeulType.SALARY),
                                      cg(CheonggeulType.FUTURE, sourced=False)))
    card = next(c for c in run(world).items if c.company_id == "t-06")
    assert [b.cheonggeul_type for b in card.badges] == [CheonggeulType.SALARY]
    assert "청끌기업 · 미래" not in card.facts


@pytest.mark.parametrize("kind, expected", [
    (CheonggeulType.SALARY, {"t-02", "t-05"}),
    ("WELFARE", {"t-03"}),
    (CheonggeulType.WORK_LIFE, {"t-04"}),
    (CheonggeulType.FUTURE, {"t-01"}),
])
def test_category_filter(world, kind, expected):
    assert set(ids(run(world, category=kind))) == expected


def test_bad_category_is_invalid_input(world):
    with pytest.raises(OppError):
        run(world, category="GROWTH")


def test_no_profile_sorts_by_name(world):
    resp = run(world, user_id="nobody")
    assert ids(resp) == ["t-01", "t-02", "t-03", "t-04", "t-05"]  # 가나 다라 마바 사아 자차
    assert all(not any(f.startswith("희망 직무") for f in c.facts) for c in resp.items)


def test_profile_without_jobs_sorts_by_name(world):
    set_profile(world, "u-empty", priorities=[])
    assert ids(run(world, user_id="u-empty")) == ["t-01", "t-02", "t-03", "t-04", "t-05"]


def test_industry_overlap_comes_first(world):
    set_profile(world, "u-acc", desired_jobs=[DesiredJob(name="사무·회계")])
    resp = run(world, user_id="u-acc")
    assert ids(resp)[0] == "t-04"
    assert "희망 직무·전공과 겹치는 낱말: 회계" in resp.items[0].facts


def test_main_product_and_major_overlap(world):
    # "데이터" → 주력 제품 "데이터 분석 플랫폼", 전공 "통계학" → "통계" → 주력 제품 "통계 조사"
    set_profile(world, "u-data", desired_jobs=[DesiredJob(name="데이터 분석")], major="통계학")
    assert ids(run(world, user_id="u-data"))[:2] == ["t-01", "t-05"]


def test_single_char_word_is_ignored(world):
    set_profile(world, "u-one", desired_jobs=[DesiredJob(name="업")])  # 한 글자는 모든 "…업"에 걸린다
    assert ids(run(world, user_id="u-one")) == ["t-01", "t-02", "t-03", "t-04", "t-05"]


@pytest.mark.parametrize("priority, first", [
    ("SALARY", ["t-02", "t-05"]),
    ("WORK_LIFE", ["t-04"]),
    ("GROWTH", ["t-01"]),  # GROWTH ↔ FUTURE
])
def test_priority_matches_cheonggeul_type(world, priority, first):
    set_profile(world, "u-pri", priorities=[priority])
    got = ids(run(world, user_id="u-pri"))
    assert got[:len(first)] == first


def test_stability_has_no_match(world):
    set_profile(world, "u-stab", priorities=["STABILITY"])
    assert ids(run(world, user_id="u-stab")) == ["t-01", "t-02", "t-03", "t-04", "t-05"]


def test_overlap_beats_priority(world):
    set_profile(world, "u-both", desired_jobs=[DesiredJob(name="회계")], priorities=["SALARY"])
    assert ids(run(world, user_id="u-both"))[:3] == ["t-04", "t-02", "t-05"]


def test_limit(world):
    assert len(run(world, limit=2).items) == 2
    assert run(world, limit=0).items == []


def test_default_limit_from_config(world):
    for i in range(world.config.companies.limit + 3):
        world.catalog.put_company(company(f"t-x{i:02d}", f"하회사{i:02d}", cg(CheonggeulType.WELFARE)))
    assert len(run(world).items) == world.config.companies.limit


def test_card_facts_are_plain_facts(world):
    card = next(c for c in run(world).items if c.company_id == "t-01")
    assert card.facts[:2] == ["청끌기업 · 미래", "해운대구"]
    assert "주력 제품: 데이터 분석 플랫폼" in card.facts
    assert "규모: 상시근로자 40명" in card.facts
    assert card.open_postings == 0
    assert (card.source, card.as_of) == (REC_SRC["source"], REC_SRC["as_of"])


def test_response_meta(world):
    resp = run(world)
    assert resp.basis == copy_rules.COMPANIES_BASIS
    assert resp.notice == copy_rules.COMPANIES_NOTICE
    assert resp.data_as_of == world.catalog.data_as_of()


BANNED = ("채용 중", "채용중", "추천", "좋은 회사", "연봉", "급여 ")


def test_no_forbidden_or_invented_copy(world):
    set_profile(world, "u-data", desired_jobs=[DesiredJob(name="데이터 분석")], priorities=["SALARY", "GROWTH"])
    resp = run(world, user_id="u-data")
    text = resp.model_dump_json(by_alias=True)
    assert copy_rules.find_forbidden(text) == []
    for card in resp.items:
        for fact in card.facts:
            assert copy_rules.find_forbidden(fact) == []
            assert not any(b in fact for b in BANNED), fact
    for b in ("채용 중", "채용중", "추천", "좋은 회사"):
        assert b not in text.replace(copy_rules.COMPANIES_NOTICE, "")
    # 점수 숫자를 싣지 않는다
    assert "score" not in text.lower()


def test_demo_world_persona(deps):
    """데모 데이터 그대로: demo1(급여·성장)은 급여 청끌기업이 먼저, 강소·이전기관만 있는 회사는 빠진다."""
    resp = companies.list_busan_companies(deps, "demo1", as_of=w.DEMO_AS_OF)
    assert ids(resp) == ["biz-DEMO000001", "biz-DEMO000002"]
    assert resp.items[0].facts[0] == "청끌기업 · 급여"


def test_name_sort_ignores_legal_marks(world):
    world.catalog.put_company(company("t-07", "(주)하늘", cg(CheonggeulType.WELFARE)))
    world.catalog.put_company(company("t-08", "㈜거북", cg(CheonggeulType.WELFARE)))
    got = ids(run(world))
    assert got.index("t-01") < got.index("t-08") < got.index("t-02")  # 가나 < 거북 < 다라
    assert got[-1] == "t-07"  # 하늘은 맨 뒤 (표기 "(주)" 때문에 앞으로 오지 않는다)
