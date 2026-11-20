"""직선거리 표시: 통근 시간이 없는 구간에서도 구청 사이 거리를 보여 준다. 이동 시간처럼 말하지 않는다."""

from opportunity.core import copy_rules, facts
from opportunity.core.local_life import build_local_life
from opportunity.core.ranking import search_postings
from opportunity.models import GuOffice, OppPrefs
from opportunity.seeds import demo_world as w


def with_offices(deps, *, source="카카오 로컬 (구·군청 위치)", as_of="2026-11-20"):
    deps.local_life.gu_offices = {
        "26290": GuOffice(sigungu="26290", name="남구", lat=35.1365, lng=129.0842),
        "26350": GuOffice(sigungu="26350", name="해운대구", lat=35.1631, lng=129.1636),
    }
    deps.local_life.gu_offices_source, deps.local_life.gu_offices_as_of = source, as_of
    deps.users.put_prefs("demo1", OppPrefs(demo_as_of=w.DEMO_AS_OF))
    return deps


def test_distance_between_gu_offices(deps):
    with_offices(deps)
    profile = deps.users.get_basic_profile("demo1")  # 남구 거주
    region = deps.catalog.get_latest(w.BUSAN_DATA).work_region  # 해운대구
    km = facts.distance_km(deps.local_life, profile, region)
    assert 7.0 <= km <= 8.5
    label = facts.distance_fact(km)
    assert label == copy_rules.DISTANCE_LABEL.format(km=f"{km:g}") and "직선거리" in label and "분" not in label


def test_no_distance_without_source_same_gu_or_unknown(deps):
    with_offices(deps, source=None)
    profile = deps.users.get_basic_profile("demo1")
    latest = deps.catalog.get_latest
    assert facts.distance_km(deps.local_life, profile, latest(w.BUSAN_DATA).work_region) is None  # 출처 없음
    with_offices(deps)
    assert facts.distance_km(deps.local_life, profile, latest(w.BUSAN_DATA_PUBLIC).work_region) is None  # 같은 구
    assert facts.distance_km(deps.local_life, profile, latest(w.DATA_UNKNOWN_REGION).work_region) is None
    assert facts.distance_km(deps.local_life, profile, latest(w.SEOUL_DATA).work_region) is None  # 구청 위치 없음


def test_card_shows_distance_only_when_no_commute_time(deps):
    with_offices(deps)
    card = next(c for c in search_postings(deps, "demo1").items if c.job_posting_id == w.BUSAN_DATA)
    assert card.distance_km is not None and any("직선거리" in f for f in card.facts)
    deps.local_life.commute_minutes = {"26290>26350": 31}
    deps.local_life.commute_source, deps.local_life.commute_as_of = "ODsay", "2026-11-20"
    card = next(c for c in search_postings(deps, "demo1").items if c.job_posting_id == w.BUSAN_DATA)
    assert card.commute_minutes == 31 and not any("직선거리" in f for f in card.facts)  # 시간이 있으면 시간만
    assert card.distance_km is not None


def test_local_life_block_includes_distance(deps):
    with_offices(deps)
    profile = deps.users.get_basic_profile("demo1")
    view = build_local_life(deps, profile, deps.catalog.get_latest(w.BUSAN_DATA))
    assert view is not None and view.distance_km is not None and "직선거리" in view.distance_label
    assert build_local_life(deps, profile, deps.catalog.get_latest(w.SEOUL_DATA)) is None
