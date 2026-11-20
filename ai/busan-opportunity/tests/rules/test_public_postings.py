"""로그인 없이 보는 공고 목록 (B-D10): 분류, 검색어, 마감 임박순, 쪽 나누기. 프로필과 사용자를 쓰지 않는다."""

import pytest
from rules.test_ncs_match import OVERSEAS_VN, add_posting

from opportunity.core import clock
from opportunity.core.public_postings import list_public_postings
from opportunity.models import OppError
from opportunity.models.enums import CareerType, EmploymentType, OrgType
from opportunity.seeds import demo_world as w


def page(deps, as_of, **kwargs):
    kwargs.setdefault("limit", 50)
    return list_public_postings(deps, as_of=as_of, **kwargs)


def ids(result):
    return [c.job_posting_id for c in result.items]


def test_lists_every_open_posting_by_deadline(deps, as_of):
    result = page(deps, as_of)
    open_rows = [n for n in deps.catalog.posting_names() if not clock.is_expired(n.closes_at, as_of)]
    assert result.total == len(result.items) == len(open_rows) > 0
    closes = [c.closes_at for c in result.items]
    assert closes == sorted(closes)  # 마감 임박순. 상시 채용(9999-12-31)은 뒤
    assert not {"matchScore", "matchLevel", "eligibility", "facts"} & set(result.to_api()["items"][0])  # 개인 값 없음


def test_region_and_org_type_filters(deps, as_of):
    add_posting(deps, "wj-PUB0001", work_region=OVERSEAS_VN)
    local = add_posting(deps, "klid-PUB0001", region=w.HAEUNDAE)
    deps.catalog.put_latest(local.model_copy(update={"org_type": OrgType.LOCAL_PUBLIC}))
    busan = page(deps, as_of, region="BUSAN")
    assert busan.items and all(c.work_region.sido == "26" for c in busan.items)
    seoul = page(deps, as_of, region="11")
    assert seoul.items and all(c.work_region.sido == "11" for c in seoul.items)
    assert ids(page(deps, as_of, region="OVERSEAS")) == ["wj-PUB0001"]
    assert "wj-PUB0001" not in ids(page(deps, as_of, region="CAPITAL"))
    assert ids(page(deps, as_of, org_type="LOCAL_PUBLIC")) == ["klid-PUB0001"]
    public = page(deps, as_of, org_type="PUBLIC_INSTITUTION")
    assert public.items and all(c.org_type == OrgType.PUBLIC_INSTITUTION for c in public.items)


def test_career_and_employment_filters(deps, as_of):
    latest = add_posting(deps, "wk24-PUB0002", region=w.GANGNAM)
    deps.catalog.put_latest(latest.model_copy(update={"career_type": CareerType.ANY,
                                                      "employment_type": EmploymentType.INTERN}))
    new, experienced = page(deps, as_of, career="NEW"), page(deps, as_of, career="EXPERIENCED")
    assert "wk24-PUB0002" in ids(new) and "wk24-PUB0002" in ids(experienced)  # 신입·경력 무관은 둘 다에 보인다
    assert all(c.career_type in (CareerType.NEW, CareerType.ANY) for c in new.items)
    assert all(c.career_type in (CareerType.EXPERIENCED, CareerType.ANY) for c in experienced.items)
    assert ids(page(deps, as_of, employment="INTERN")) == ["wk24-PUB0002"]


def test_keyword_matches_title_organization_and_job_name(deps, as_of):
    latest = add_posting(deps, "wk24-PUB0003", region=w.GANGNAM)
    deps.catalog.put_latest(latest.model_copy(update={"organization": "(주)가상전자"}))
    assert ids(page(deps, as_of, keyword="가상전자")) == ["wk24-PUB0003"]
    assert page(deps, as_of, keyword="없는회사").total == 0


def test_pages_follow_the_cursor(deps, as_of):
    first = page(deps, as_of, limit=3)
    second = page(deps, as_of, limit=3, cursor=first.next_cursor)
    assert first.next_cursor and len(first.items) == 3 and second.total == first.total
    assert ids(first) + ids(second) == ids(page(deps, as_of))[:6]


def test_closed_postings_are_left_out(deps, as_of):
    add_posting(deps, "wk24-PUB0004", region=w.GANGNAM, closes="2026-11-01")
    assert "wk24-PUB0004" not in ids(page(deps, as_of))


def test_all_means_no_filter(deps, as_of):
    assert page(deps, as_of, org_type="ALL", career="all", employment="ALL").total == page(deps, as_of).total


@pytest.mark.parametrize("kwargs", [{"org_type": "COMPANY"}, {"career": "SENIOR"}, {"employment": "FREELANCE"},
                                    {"region": "MARS"}, {"limit": 0}, {"limit": 51}])
def test_bad_values_are_400(deps, as_of, kwargs):
    with pytest.raises(OppError) as error:
        list_public_postings(deps, as_of=as_of, **kwargs)
    assert error.value.status == 400


def test_sector_splits_public_and_private(deps, as_of):
    """공기업 = 공공기관 + 지방공공기관, 사기업 = 민간 기업 (B-D10). 둘을 합치면 전체다."""
    local = add_posting(deps, "klid-PUB0005", region=w.HAEUNDAE)
    deps.catalog.put_latest(local.model_copy(update={"org_type": OrgType.LOCAL_PUBLIC}))
    public, private = page(deps, as_of, sector="PUBLIC"), page(deps, as_of, sector="private")
    assert {c.org_type for c in public.items} == {OrgType.PUBLIC_INSTITUTION, OrgType.LOCAL_PUBLIC}
    assert {c.org_type for c in private.items} == {OrgType.PRIVATE}
    assert public.total + private.total == page(deps, as_of).total
    with pytest.raises(OppError):
        page(deps, as_of, sector="GOVERNMENT")
