"""배지와 지역인재."""

from unit.enrich import factories as f

from opportunity.enrich.badges import build_badges, find_company, normalize_name
from opportunity.enrich.regional_talent import find_basis, judge_posting_regional_talent, judge_regional_talent
from opportunity.models.enums import BadgeType, OrgType, RegionalBenefitKind, RegionalTalentStatus, RemoteWork
from opportunity.models.posting import Badge, CompanyRecord
from opportunity.seeds import demo_world as w


def test_normalize_name():
    assert normalize_name("(주)가상데이터") == normalize_name("가상데이터 주식회사") == normalize_name("㈜ 가상 데이터")
    assert normalize_name("가상데이터") != normalize_name("가상데이터랩")


def test_badge_matched_by_company_id(deps):
    snap = f.snapshot(org="전혀 다른 이름", company_id="biz-DEMO000001")
    badges = build_badges(deps, snap)
    assert [b.type for b in badges] == [BadgeType.CHEONGKKEUL]
    assert all(b.source and b.as_of for b in badges)


def test_badge_matched_by_normalized_name(deps):
    snap = f.snapshot(org="가상상사 주식회사")
    badges = build_badges(deps, snap)
    assert badges and badges[0].label == w.BADGE_CG_WORKLIFE.label
    assert badges[0].source == w.CHEONGGEUL_SRC["source"] and badges[0].as_of == w.CHEONGGEUL_SRC["as_of"]


def test_badge_matched_by_biz_no(deps):
    deps.catalog.put_company(CompanyRecord(company_id="biz-TEST1", name="시드 이름", biz_no="123-45-67890", sido="26",
                                           highlights=[w.BADGE_GANGSO], source="고용노동부 (데모)",
                                           as_of="2026-06-30"))
    snap = f.snapshot(org="공고에 적힌 다른 이름", biz_no="1234567890")
    assert find_company(deps, snap).company_id == "biz-TEST1"
    assert [b.type for b in build_badges(deps, snap)] == [BadgeType.GANGSO]


def test_same_name_but_different_biz_no_is_not_matched(deps):
    deps.catalog.put_company(CompanyRecord(company_id="biz-TEST2", name="(주)동명", biz_no="111-11-11111", sido="26",
                                           highlights=[w.BADGE_GANGSO], source="고용노동부 (데모)",
                                           as_of="2026-06-30"))
    assert find_company(deps, f.snapshot(org="동명 주식회사", biz_no="222-22-22222")) is None


def test_t08_no_badge_without_seed_or_source(deps):
    # 시드에 없는 기업: 원래 붙어 있던 출처 없는 배지도 다시 만들지 않는다
    snap = f.snapshot(org="(주)시드에없음").model_copy(update={"badges": [w.BADGE_NO_SOURCE]})
    assert build_badges(deps, snap) == []
    # 시드에 있어도 출처·기준일이 비어 있으면 붙이지 않는다
    deps.catalog.put_company(CompanyRecord(company_id="biz-TEST3", name="출처빈기업", sido="26",
                                           highlights=[Badge(type=BadgeType.CHEONGKKEUL, label="청끌기업")],
                                           source="", as_of=""))
    assert build_badges(deps, f.snapshot(org="출처빈기업")) == []


def test_remote_badge_only_for_full_or_hybrid(deps):
    for remote, expected in ((RemoteWork.FULL, True), (RemoteWork.HYBRID, True), (RemoteWork.NONE, False),
                             (RemoteWork.UNKNOWN, False)):
        badges = build_badges(deps, f.snapshot(org="(주)시드에없음", region=f.GANGNAM, remote=remote))
        remote_badges = [b for b in badges if b.type == BadgeType.REMOTE_WORK]
        assert bool(remote_badges) is expected
        assert all(b.source and b.as_of == "2026-11-21" for b in remote_badges)


def _judge(deps, snap, text):
    company = find_company(deps, snap)
    relocated = bool(company and company.regional_talent)
    return judge_posting_regional_talent(deps.config, snap, text, relocated=relocated,
                                         relocated_sido=company.sido if relocated else None)


def test_regional_talent_likely_with_basis(deps):
    text = "기금 운용 데이터를 분석한다.\n이전지역인재 채용목표제를 적용하며 지역인재는 서류전형 가점 5%를 준다."
    snap = f.snapshot(org="가상금융공사", org_type=OrgType.PUBLIC_INSTITUTION, description=text)
    result = _judge(deps, snap, text)
    assert result.status == RegionalTalentStatus.LIKELY
    assert result.basis == "이전지역인재 채용목표제를 적용하며 지역인재는 서류전형 가점 5%를 준다."
    # 지역을 적지 않은 이전지역인재는 부산 이전기관이라 부산 학교로 본다
    assert [(c.kind, c.sido) for c in result.conditions] == [(RegionalBenefitKind.SCHOOL, "26")]


def test_regional_talent_check_needed_for_relocated_without_mention(deps):
    snap = f.snapshot(org="가상해양공단", org_type=OrgType.PUBLIC_INSTITUTION, description="공단 행정 업무")
    result = _judge(deps, snap, "공단 행정 업무")
    assert result.status == RegionalTalentStatus.CHECK_NEEDED and result.basis is None and result.conditions == []


def test_regional_talent_for_others_reads_the_posting(deps):
    """이전기관이 아니어도 공고문에 지역 조건이 있으면 읽는다. 지역을 적지 않았으면 UNKNOWN이다."""
    result = _judge(deps, f.snapshot(org="(주)가상데이터"), "지역인재 우대")
    assert result.status == RegionalTalentStatus.LIKELY
    assert [c.kind for c in result.conditions] == [RegionalBenefitKind.UNKNOWN]
    assert judge_regional_talent("데이터 분석 업무").status == RegionalTalentStatus.NOT_APPLICABLE


def test_find_basis_returns_sentence():
    assert find_basis("업무 소개. 채용목표제 적용 기관입니다. 끝") == "채용목표제 적용 기관입니다."
    assert find_basis("자격증 가점 있음") is None
