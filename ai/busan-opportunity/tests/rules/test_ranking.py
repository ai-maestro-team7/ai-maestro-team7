"""피드 규칙 (B-03, §4.4, §4.5). T-01, T-02, T-04, T-08, T-21."""

import itertools

import pytest

from opportunity.core import copy_rules, eligibility, ranking
from opportunity.models import MatchLevel, OppError, Sort
from opportunity.models.posting import Job, Salary, WorkRegion
from opportunity.models.profile import BasicProfile, DesiredJob
from opportunity.seeds import demo_world as w

PERSONAS = ("demo1", "demo2", "demo3")


def feed(deps, as_of, user="demo1", **kwargs):
    kwargs.setdefault("limit", 100)
    return ranking.search_postings(deps, user, as_of=as_of, **kwargs)


def ids(response):
    return [c.job_posting_id for c in response.items]


class IgnoreFilterVectors:
    """메타데이터가 늦게 갱신돼 필터가 마감 공고를 못 거르는 상황을 흉내 낸다."""

    def __init__(self, inner):
        self.inner = inner

    def query(self, vector, *, top_k, filter=None):
        return self.inner.query(vector, top_k=top_k, filter=None)

    def __getattr__(self, name):
        return getattr(self.inner, name)


# ---------------------------------------------------------------- T-01
@pytest.mark.parametrize("user", PERSONAS)
def test_t01_busan_first_and_match_have_same_set(deps, as_of, user):
    busan_first = feed(deps, as_of, user, sort=Sort.BUSAN_FIRST)
    match = feed(deps, as_of, user, sort=Sort.MATCH)
    assert busan_first.items
    assert set(ids(busan_first)) == set(ids(match))
    assert len(ids(busan_first)) == len(set(ids(busan_first)))


def test_t01_only_rank_differs(deps, as_of):
    busan_first = {c.job_posting_id: c for c in feed(deps, as_of, sort=Sort.BUSAN_FIRST).items}
    match = {c.job_posting_id: c for c in feed(deps, as_of, sort=Sort.MATCH).items}
    boost = deps.config.ranking.busan_boost
    for pid, card in busan_first.items():
        assert card.match_score == match[pid].match_score  # 적합도는 정렬과 상관없다
        assert match[pid].rank_score == match[pid].match_score
        expected = card.match_score + boost if card.is_busan and card.match_score >= deps.config.ranking.boost_min_match \
            else card.match_score
        assert card.rank_score == pytest.approx(expected, abs=1e-3)


def test_ranking_basis_chip(deps, as_of):
    busan_first = feed(deps, as_of, sort=Sort.BUSAN_FIRST).ranking
    assert busan_first.basis == copy_rules.RANKING_BASIS[Sort.BUSAN_FIRST]
    assert busan_first.busan_boost == deps.config.ranking.busan_boost
    for sort in (Sort.MATCH, Sort.DEADLINE, Sort.RECENT):
        ranking_info = feed(deps, as_of, sort=sort).ranking
        assert ranking_info.basis == copy_rules.RANKING_BASIS[sort] and ranking_info.busan_boost is None


def test_sort_defaults_to_user_preference(deps, as_of):
    prefs = deps.users.get_prefs("demo1").model_copy(update={"sort": Sort.DEADLINE})
    deps.users.put_prefs("demo1", prefs)
    assert feed(deps, as_of).ranking.sort == Sort.DEADLINE


# ---------------------------------------------------------------- T-02
def test_t02_rank_score_never_inverts_guard(config):
    guard = config.ranking.inversion_guard
    grid = [i / 100 for i in range(101)]
    for busan_match, other_match in itertools.product(grid, grid):
        if other_match - busan_match >= guard:
            busan = ranking.rank_score(config, busan_match, is_busan=True, sort=Sort.BUSAN_FIRST)
            other = ranking.rank_score(config, other_match, is_busan=False, sort=Sort.BUSAN_FIRST)
            assert other > busan


@pytest.mark.parametrize("user", PERSONAS)
def test_t02_better_non_busan_is_above_in_feed(deps, as_of, user):
    items = feed(deps, as_of, user, sort=Sort.BUSAN_FIRST).items
    guard = deps.config.ranking.inversion_guard
    checked = 0
    for i, j in itertools.combinations(range(len(items)), 2):
        a, b = items[i], items[j]
        for busan, other, busan_pos, other_pos in ((a, b, i, j), (b, a, j, i)):
            if busan.is_busan and not other.is_busan and other.match_score - busan.match_score >= guard:
                assert other_pos < busan_pos
                checked += 1
    assert checked  # 데모 데이터에 이런 쌍이 실제로 있다


def test_rank_score_boost_conditions(config):
    boost, low = config.ranking.busan_boost, config.ranking.boost_min_match
    assert ranking.rank_score(config, low, is_busan=True, sort=Sort.BUSAN_FIRST) == pytest.approx(low + boost)
    assert ranking.rank_score(config, low - 0.01, is_busan=True, sort=Sort.BUSAN_FIRST) == low - 0.01
    assert ranking.rank_score(config, 0.8, is_busan=False, sort=Sort.BUSAN_FIRST) == 0.8
    for sort in (Sort.MATCH, Sort.DEADLINE, Sort.RECENT):
        assert ranking.rank_score(config, 0.8, is_busan=True, sort=sort) == 0.8


# ---------------------------------------------------------------- T-04
@pytest.mark.parametrize("user", PERSONAS)
def test_t04_is_busan_does_not_change_match_score(deps, user):
    profile = deps.users.get_basic_profile(user)
    busan = WorkRegion(sido="26", sigungu="26350", label="부산 해운대구")
    seoul = WorkRegion(sido="11", sigungu="11680", label="서울 강남구")
    for posting in deps.catalog.latest.values():
        result = eligibility.judge(deps, profile, posting.eligibility_rules)
        scores = set()
        for is_busan, region in ((True, busan), (False, seoul)):
            flipped = posting.model_copy(update={"is_busan": is_busan, "work_region": region,
                                                 "is_capital_area": not is_busan})
            scores.add(ranking.match_score(deps.config, profile, flipped, content_similarity=0.7,
                                           eligibility=result).score)
        assert len(scores) == 1, posting.job_posting_id


# ---------------------------------------------------------------- 적합도 항목
def test_job_match_levels(config):
    levels = config.match.job_match_levels
    job = Job(code="D0101", middle="D01", major="D", name="데이터 분석가")

    def value(*desired):
        return ranking.job_match_value(config, BasicProfile(desired_jobs=list(desired)), job)

    assert value(DesiredJob(work24_code="D0101", name="x")) == levels.exact
    assert value(DesiredJob(work24_code="D0102", name="x")) == levels.same_middle
    assert value(DesiredJob(work24_code="D0201", name="x")) == levels.same_major
    assert value(DesiredJob(work24_code="A0201", name="x")) == 0
    assert value(DesiredJob(work24_code="A0201", name="x"), DesiredJob(work24_code="D0102", name="y")) \
        == levels.same_middle  # 여러 개면 가장 높은 값
    assert value(DesiredJob(name="데이터 분석")) == levels.exact  # 코드 없으면 이름 포함 관계
    assert value(DesiredJob(name="회계")) == 0
    assert value() is None


def test_content_sim_range(config):
    low, high = config.match.content_sim_range.low, config.match.content_sim_range.high
    assert ranking.content_sim_value(config, low) == 0
    assert ranking.content_sim_value(config, low - 0.1) == 0
    assert ranking.content_sim_value(config, high) == 1
    assert ranking.content_sim_value(config, (low + high) / 2) == pytest.approx(0.5)
    assert ranking.content_sim_value(config, None) is None


def test_preferred_ok_needs_known_skills(deps):
    posting = deps.catalog.get_latest(w.BUSAN_DATA)  # 우대 ADsP, 급여 기재, 청끌 급여
    no_skills = BasicProfile(priorities=["SALARY", "GROWTH"])
    assert ranking.preferred_ok_value(no_skills, posting) == 0.5  # 우대 요건은 미확인이라 빼고 중요 조건만
    with_cert = BasicProfile(priorities=["SALARY", "GROWTH"], certificates=["ADsP"])
    assert ranking.preferred_ok_value(with_cert, posting) == pytest.approx((1.0 + 0.5) / 2)
    assert ranking.preferred_ok_value(BasicProfile(), posting) is None


def test_priority_checks(deps):
    stability = BasicProfile(priorities=["STABILITY"])
    worklife = BasicProfile(priorities=["WORK_LIFE"])
    growth = BasicProfile(priorities=["GROWTH"])
    latest = deps.catalog.get_latest
    assert ranking.preferred_ok_value(stability, latest(w.BUSAN_ADMIN_PUBLIC)) == 1
    assert ranking.preferred_ok_value(worklife, latest(w.BUSAN_ACCOUNT)) == 1      # 청끌 워라밸
    assert ranking.preferred_ok_value(worklife, latest(w.SEOUL_DATA_HYBRID)) == 1  # 원격 근무
    assert ranking.preferred_ok_value(worklife, latest(w.SEOUL_DATA)) == 0
    assert ranking.preferred_ok_value(growth, latest(w.BUSAN_DATA_PUBLIC)) == 1    # 이전기관
    assert ranking.preferred_ok_value(growth, latest(w.BUSAN_DATA)) == 0
    assert ranking.preferred_ok_value(BasicProfile(priorities=["UNKNOWN_KEY"]), latest(w.BUSAN_DATA)) is None


def test_unmeasured_items_are_reweighted(deps):
    cfg = deps.config
    weights = cfg.match.weights
    profile = deps.users.get_basic_profile("demo1")
    posting = deps.catalog.get_latest(w.BUSAN_DATA)
    only_job = ranking.match_score(cfg, BasicProfile(desired_jobs=profile.desired_jobs), posting)
    assert only_job.content_sim is None and only_job.required_ok is None and only_job.preferred_ok is None
    assert only_job.score == pytest.approx(cfg.match.job_match_levels.exact)
    full = ranking.match_score(cfg, profile, posting, content_similarity=cfg.match.content_sim_range.high,
                               eligibility=eligibility.judge(deps, profile, posting.eligibility_rules))
    expected = (weights.job_match * 1 + weights.content_sim * 1 + weights.required_ok * 1
                + weights.preferred_ok * full.preferred_ok)
    assert full.score == pytest.approx(expected)
    assert ranking.match_score(cfg, BasicProfile(), posting.model_copy(update={"salary": Salary()})).score == 0


def test_match_level_thresholds(config):
    good, fair = config.match.levels.good, config.match.levels.fair
    assert ranking.match_level(config, good) == MatchLevel.GOOD
    assert ranking.match_level(config, fair) == MatchLevel.FAIR
    assert ranking.match_level(config, fair - 0.01) == MatchLevel.LOW


# ---------------------------------------------------------------- T-08, T-21
def test_t08_feed_drops_badge_without_source(deps, as_of):
    cards = {c.job_posting_id: c for c in feed(deps, as_of, "demo2").items}
    assert w.BUSAN_BADGE_NO_SOURCE in cards
    assert cards[w.BUSAN_BADGE_NO_SOURCE].badges == []
    assert all(b.source and b.as_of for c in cards.values() for b in c.badges)


def test_t21_feed_drops_closed_postings(deps, as_of):
    for user in PERSONAS:
        got = set(ids(feed(deps, as_of, user)))
        assert w.BUSAN_DATA_EXPIRED not in got and w.BUSAN_DATA_JUST_CLOSED not in got


def test_t21_feed_drops_closed_even_if_vector_filter_misses(deps, as_of):
    deps.vectors = IgnoreFilterVectors(deps.vectors)
    got = set(ids(feed(deps, as_of)))
    assert w.BUSAN_DATA in got
    assert w.BUSAN_DATA_EXPIRED not in got and w.BUSAN_DATA_JUST_CLOSED not in got  # 9번은 isExpired가 아직 false


# ---------------------------------------------------------------- 근무지 미상
def test_unknown_region_is_not_counted_as_busan(deps, as_of):
    cards = {c.job_posting_id: c for c in feed(deps, as_of, sort=Sort.BUSAN_FIRST).items}
    unknown = cards[w.DATA_UNKNOWN_REGION]
    assert not unknown.is_busan and not unknown.is_capital_area
    assert unknown.rank_score == unknown.match_score  # 가산점 없음
    assert w.DATA_UNKNOWN_REGION not in ids(feed(deps, as_of, region="BUSAN"))
    assert w.DATA_UNKNOWN_REGION not in ids(feed(deps, as_of, region="CAPITAL"))


# ---------------------------------------------------------------- 거르기, 쪽 나누기
def test_region_filter(deps, as_of):
    busan = feed(deps, as_of, region="BUSAN").items
    assert busan and all(c.is_busan for c in busan)
    capital = feed(deps, as_of, region="CAPITAL").items
    assert capital and all(c.is_capital_area for c in capital)
    seoul = feed(deps, as_of, region="11").items
    assert seoul and all(c.work_region.sido == "11" for c in seoul)
    with pytest.raises(OppError) as e:
        feed(deps, as_of, region="MOON")
    assert e.value.code == "INVALID_INPUT"


def test_job_codes_and_keyword(deps, as_of):
    by_code = feed(deps, as_of, job_codes=["D01"]).items
    assert by_code and all(c.job.middle == "D01" for c in by_code)
    exact = feed(deps, as_of, job_codes=["D0101"]).items
    assert exact and all(c.job.code == "D0101" for c in exact)
    keyword = feed(deps, as_of, keyword="data").items
    assert ids_of(keyword) == {w.SEOUL_DATA}


def ids_of(cards):
    return {c.job_posting_id for c in cards}


def test_sort_deadline_and_recent(deps, as_of):
    deadline = feed(deps, as_of, sort=Sort.DEADLINE).items
    assert [c.closes_at for c in deadline] == sorted(c.closes_at for c in deadline)
    latest = deps.catalog.get_latest(w.BUSAN_BACKEND)
    deps.catalog.put_latest(latest.model_copy(update={"checked_at": "2026-11-21T09:30:00+09:00"}))
    assert feed(deps, as_of, sort=Sort.RECENT).items[0].job_posting_id == w.BUSAN_BACKEND


def test_cursor_pages_cover_the_same_set(deps, as_of):
    full = ids(feed(deps, as_of))
    seen, cursor = [], None
    while True:
        page = feed(deps, as_of, limit=4, cursor=cursor)
        seen += ids(page)
        cursor = page.next_cursor
        if cursor is None:
            break
        assert "offset" not in cursor  # 불투명 문자열
    assert seen == full
    with pytest.raises(OppError) as e:
        feed(deps, as_of, cursor="not-a-cursor")
    assert e.value.code == "INVALID_INPUT"


def test_profile_without_jobs_is_incomplete(deps, as_of):
    deps.users.profiles["empty"] = BasicProfile(major="통계학")
    with pytest.raises(OppError) as e:
        feed(deps, as_of, "empty")
    assert e.value.code == "PROFILE_INCOMPLETE" and e.value.status == 422


def test_ask_leave_reason_only_once_for_capital(deps, as_of):
    assert feed(deps, as_of, region="ALL").ask_leave_reason is False
    assert feed(deps, as_of, region="CAPITAL").ask_leave_reason is True
    assert feed(deps, as_of, region="CAPITAL").ask_leave_reason is False


def test_capital_cards_have_busan_alternatives_count(deps, as_of):
    cards = {c.job_posting_id: c for c in feed(deps, as_of).items}
    assert cards[w.SEOUL_DATA].busan_alternatives_count == 2  # 마감·유사도 미달 후보는 세지 않는다
    assert cards[w.SEOUL_GAME].busan_alternatives_count == 0
    assert cards[w.GYEONGGI_DATA_ENG].busan_alternatives_count is None  # ALTS 없음
    assert all(c.busan_alternatives_count is None for c in cards.values() if not c.is_capital_area)
    assert all(c.busan_alternatives_count <= deps.config.alternatives.view_max
               for c in cards.values() if c.busan_alternatives_count is not None)


def test_card_facts_and_freshness(deps, as_of):
    response = feed(deps, as_of)
    card = next(c for c in response.items if c.job_posting_id == w.BUSAN_DATA)
    assert card.facts == ["희망 직무와 같은 직종", "필수 조건 2개 중 2개 충족", "마감 D-14"]
    assert card.eligibility is not None and card.is_sample
    assert response.data_as_of == w.DATA_AS_OF and response.stale is False
    for c in response.items:
        for text in c.facts:
            assert not copy_rules.find_forbidden(text)
    late = feed(deps, "2026-11-24T10:00:00+09:00")
    assert late.stale is True


def test_empty_busan_message_when_no_close_busan_job(deps, as_of):
    assert feed(deps, as_of).empty_message is None
    deps.users.profiles["game"] = BasicProfile(desired_jobs=[DesiredJob(work24_code="G0301", name="게임 클라이언트")])
    assert feed(deps, as_of, "game").empty_message == copy_rules.EMPTY_BUSAN
    assert feed(deps, as_of, "game", region="CAPITAL").empty_message is None
