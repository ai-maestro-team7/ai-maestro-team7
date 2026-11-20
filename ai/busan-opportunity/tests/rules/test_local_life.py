"""부산 공고 상세의 "이 동네에서 일하면" (`core/local_life.py`).

부산 근무 공고에만 붙고, 홍보처럼 보이지 않게 config 상한만큼만 보여 준다. 통근은 표에 있을 때만.
"""

import pytest

from opportunity.core import copy_rules, local_life, ranking
from opportunity.models.posting import WorkRegion
from opportunity.models.region import FestivalInfo, LocalLifeData, TransitInfo
from opportunity.seeds import demo_world as w

DAY = "2026-11-20"
SRC = {"source": "부산광역시 부산축제정보", "as_of": DAY}


def fest(fid, gugun):
    return FestivalInfo(festival_id=fid, title=f"축제 {fid}", gugun=gugun, period="2026. 5. 1. ~ 5. 3.", **SRC)


def transit(n):
    return [TransitInfo(label=f"교통 {i}", value=str(i), source="출처", as_of=DAY) for i in range(n)]


@pytest.fixture
def life(deps):
    deps.local_life = LocalLifeData(
        festivals=[fest("fest-1", "중구"), fest("fest-2", "수영구"), fest("fest-3", "해운대구"),
                   fest("fest-4", "중구"), fest("fest-5", "해운대구"), fest("fest-6", "해운대구")],
        transit=transit(5),
    )
    return deps


def build(deps, pid, user="demo1", as_of=w.DEMO_AS_OF):
    posting = deps.catalog.get_latest(pid)
    return local_life.build_local_life(deps, deps.users.get_basic_profile(user), posting, as_of=as_of)


def test_busan_posting_gets_capped_view(life):
    view = build(life, w.BUSAN_DATA)  # 해운대구
    cfg = life.config.local_life
    assert view is not None
    assert len(view.festivals) == cfg.festival_max <= 6
    assert len(view.transit) == cfg.transit_max < 5


def test_work_gugun_festivals_come_first(life):
    view = build(life, w.BUSAN_DATA)
    assert all(f.gugun == "해운대구" for f in view.festivals)
    assert [f.festival_id for f in view.festivals] == ["fest-3", "fest-5"][:life.config.local_life.festival_max]


def test_fills_from_rest_of_busan_when_gugun_has_few(life):
    limits = life.config.local_life.model_copy(update={"festival_max": 3})
    life.config = life.config.model_copy(update={"local_life": limits})
    life.local_life.festivals = [fest("fest-1", "중구"), fest("fest-3", "해운대구"), fest("fest-2", "수영구")]
    view = build(life, w.BUSAN_DATA)
    assert [f.festival_id for f in view.festivals] == ["fest-3", "fest-1", "fest-2"]


def test_no_gugun_uses_busan_wide(life):
    view = local_life.build_local_life(
        life, life.users.get_basic_profile("demo1"),
        life.catalog.get_latest(w.BUSAN_DATA).model_copy(update={"work_region": WorkRegion(sido="26", label="부산")}),
    )
    assert [f.festival_id for f in view.festivals] == ["fest-1", "fest-2"][:life.config.local_life.festival_max]


def test_gugun_from_label_when_code_missing():
    assert local_life.gugun_name(WorkRegion(sido="26", label="부산 해운대구")) == "해운대구"
    assert local_life.gugun_name(WorkRegion(sido="26", sigungu="26710")) == "기장군"
    assert local_life.gugun_name(WorkRegion(sido="26", label="부산")) is None
    assert len(local_life.BUSAN_GUGUN) == 16


@pytest.mark.parametrize("pid", [w.SEOUL_DATA, w.GYEONGGI_DATA_ENG, w.DATA_UNKNOWN_REGION])
def test_non_busan_gets_none(life, pid):
    assert build(life, pid) is None


def test_overseas_gets_none(life):
    posting = life.catalog.get_latest(w.BUSAN_DATA).model_copy(
        update={"work_region": WorkRegion(sido="26", label="해외", overseas=True, country="베트남")})
    assert local_life.build_local_life(life, life.users.get_basic_profile("demo1"), posting) is None


def test_empty_data_gives_none(deps):
    assert build(deps, w.BUSAN_DATA) is None


def test_items_without_source_are_dropped(life):
    life.local_life.festivals = [FestivalInfo(festival_id="fest-x", title="가", gugun="해운대구", source="", as_of=DAY)]
    life.local_life.transit = [TransitInfo(label="가", value="1", source="출처", as_of="")]
    assert build(life, w.BUSAN_DATA) is None


def test_commute_only_when_in_table(life):
    assert build(life, w.BUSAN_DATA).commute_minutes is None  # 표가 비면 추정하지 않는다
    life.local_life.commute_minutes = {"26290>26350": 42}
    life.local_life.commute_source, life.local_life.commute_as_of = "길찾기 표", DAY
    view = build(life, w.BUSAN_DATA)  # demo1은 남구(26290) 거주, 공고는 해운대구(26350)
    assert view.commute_minutes == 42
    assert view.commute_label == copy_rules.COMMUTE_LABEL.format(minutes=42)
    assert view.commute_source == "길찾기 표"
    assert build(life, w.BUSAN_DATA, user="demo2").commute_minutes is None  # 사하구 거주 쌍은 표에 없다


def test_commute_without_source_is_not_shown(life):
    life.local_life.commute_minutes = {"26290>26350": 42}
    assert build(life, w.BUSAN_DATA).commute_minutes is None


def test_commute_alone_is_enough(deps):
    deps.local_life = LocalLifeData(commute_minutes={"26290>26350": 42}, commute_source="길찾기 표",
                                    commute_as_of=DAY)
    view = build(deps, w.BUSAN_DATA)
    assert view.commute_minutes == 42 and view.festivals == [] and view.transit == []


def test_copy_has_no_forbidden_words(life):
    life.local_life.commute_minutes = {"26290>26350": 42}
    life.local_life.commute_source, life.local_life.commute_as_of = "길찾기 표", DAY
    view = build(life, w.BUSAN_DATA)
    assert not copy_rules.find_forbidden(view.commute_label)


def test_feed_cards_have_no_local_life(life):
    response = ranking.search_postings(life, "demo1", as_of=w.DEMO_AS_OF, limit=100)
    assert response.items and "localLife" not in str(response.to_api())
