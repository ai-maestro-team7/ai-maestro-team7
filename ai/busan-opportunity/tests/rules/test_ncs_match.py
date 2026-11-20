"""NCS 코드로 재는 직무 일치 (B-03 jobMatch). 실제 공공기관 공고에는 고용24 직종 코드가 없고 NCS 코드만 있다.

- 프로필 `desiredJobs[].ncsCode`: 8자리 (대분류 2 + 중분류 2 + 소분류 2 + 세분류 2)
- 공고 `job.ncsCodes`: 8자리 NCS 또는 잡알리오 코드 `R6000NN` (NN = NCS 대분류)

다른 테스트 파일도 `add_posting`으로 공고를 deps에 넣는다 (demo_world는 고치지 않는다).
"""

import pytest

from opportunity.core import facts, ranking
from opportunity.core.texts import posting_text
from opportunity.models.posting import Job, VectorMeta, WorkRegion, latest_from_snapshot
from opportunity.models.profile import BasicProfile, DesiredJob
from opportunity.seeds import demo_world as w

DATA_DESC = "데이터 분석과 통계 모델링으로 서비스 지표를 분석하고 SQL로 데이터를 다룬다"
NCS_DATA = "20010105"  # 페르소나 ① 희망 직무
ALIO_IT = Job(major="정보통신", name="정보통신", ncs_codes=["R600020"])            # 실제 잡알리오 공고 모양
ALIO_OFFICE = Job(major="경영.회계.사무", name="경영.회계.사무", ncs_codes=["R600002"])
OVERSEAS_VN = WorkRegion(label="해외 · 베트남", unknown=True, overseas=True, country="베트남")


def add_posting(deps, pid, *, region=w.HAEUNDAE, job=ALIO_IT, work_region=None, description=DATA_DESC,
                salary=(3400, 3800), closes="2026-12-06", **kwargs):
    """공고 한 건을 catalog(SNAP·LATEST)와 벡터 인덱스에 넣고 LATEST를 돌려준다."""
    snap = w._posting(pid, f"{pid} 채용", f"가상기관 {pid}", region, w.JOB_DATA, salary=salary, closes=closes,
                      description=description, **kwargs)
    update = {"job": job}
    if work_region is not None:
        update["work_region"] = work_region
    snap = snap.model_copy(update=update)
    cfg = deps.config.data
    latest = latest_from_snapshot(snap, busan_sido=cfg.busan_sido, capital_sido=cfg.capital_area_sido)
    deps.catalog.put_snapshot(snap)
    deps.catalog.put_latest(latest)
    meta = VectorMeta(is_busan=latest.is_busan, sido=latest.work_region.sido or "", job_major=snap.job.major or "",
                      active=True, deadline=int(snap.closes_at.replace("-", "")), title=snap.title)
    deps.vectors.put(pid, deps.embedder.embed(posting_text(snap)), meta.to_api())
    return latest


def value(config, job, *desired):
    return ranking.job_match_value(config, BasicProfile(desired_jobs=list(desired)), job)


def ncs_only(code):
    return DesiredJob(ncs_code=code, name="")  # 이름 비교가 끼지 않게 이름을 비운다


# ---------------------------------------------------------------- 8자리 NCS
def test_ncs_exact_middle_major(config):
    levels = config.match.job_match_levels
    assert value(config, Job(name="", ncs_codes=["20010105"]), ncs_only(NCS_DATA)) == levels.exact
    assert value(config, Job(name="", ncs_codes=["20010201"]), ncs_only(NCS_DATA)) == levels.same_middle
    assert value(config, Job(name="", ncs_codes=["20010106"]), ncs_only(NCS_DATA)) == levels.same_middle  # 소분류까지 같아도 세분류가 다르면 중분류 단계
    assert value(config, Job(name="", ncs_codes=["20020101"]), ncs_only(NCS_DATA)) == levels.same_major
    assert value(config, Job(name="", ncs_codes=["02030201"]), ncs_only(NCS_DATA)) == 0


def test_alio_code_is_at_most_category_only_major(config):
    """대분류 분류만 있는 공고는 대분류가 같으면 sameMajorCategoryOnly다. 그 위(중분류·세분류)로는 못 간다 (B-D07)."""
    levels = config.match.job_match_levels
    assert value(config, ALIO_IT, ncs_only(NCS_DATA)) == levels.same_major_category_only       # R600020 = 20 정보통신
    assert value(config, ALIO_OFFICE, ncs_only("02030201")) == levels.same_major_category_only  # R600002 = 02 경영·회계·사무
    assert value(config, ALIO_OFFICE, ncs_only(NCS_DATA)) == 0
    assert levels.same_major <= levels.same_major_category_only < levels.exact


def test_posting_with_finer_code_keeps_plain_same_major(config):
    """8자리 NCS가 있는 공고는 더 잘게 비교할 수 있으므로 대분류만 같으면 그대로 sameMajor다."""
    levels = config.match.job_match_levels
    assert value(config, Job(name="", ncs_codes=["20020101"]), ncs_only(NCS_DATA)) == levels.same_major
    mixed = Job(name="", ncs_codes=["R600020", "20020101"])  # 잡알리오 코드와 8자리가 섞이면 대분류만 아는 공고가 아니다
    assert value(config, mixed, ncs_only(NCS_DATA)) == levels.same_major
    profile = BasicProfile(desired_jobs=[ncs_only(NCS_DATA)])
    assert ranking.job_match_detail(config, profile, ALIO_IT) == (levels.same_major_category_only, ranking.BASIS_NCS_MAJOR)


def test_category_only_match_is_still_described_as_major(config):
    """점수는 올라가도 화면 문구는 "NCS 대분류"다. 중분류가 같다고 말하지 않는다."""
    levels = config.match.job_match_levels
    for basis in (ranking.BASIS_NCS_MAJOR, ranking.BASIS_NCS_MAJOR_NAME):
        assert facts.job_fact(config, levels.same_major_category_only, basis=basis) == facts.FACT_JOB_NCS_MAJOR


def test_any_of_many_categories_is_enough(config):
    levels = config.match.job_match_levels
    many = Job(name="", ncs_codes=["R600006", "R600002", "20010105"])
    assert value(config, many, ncs_only(NCS_DATA)) == levels.exact
    assert value(config, Job(name="", ncs_codes=["R600006", "R600020"]), ncs_only(NCS_DATA)) \
        == levels.same_major_category_only
    assert value(config, Job(name="", ncs_codes=["R600006", "R600011"]), ncs_only(NCS_DATA)) == 0


def test_none_only_when_nothing_to_compare(config):
    assert value(config, Job(name=""), ncs_only(NCS_DATA)) is None                 # 공고에 코드도 이름도 없음
    assert value(config, Job(name="", ncs_codes=["X1"]), ncs_only(NCS_DATA)) is None  # 모르는 코드 모양
    assert value(config, ALIO_IT, DesiredJob(name="")) is None                     # 희망 직무 NCS·이름 없음
    assert value(config, ALIO_IT, ncs_only("2001")) is None                        # 8자리가 아님
    assert value(config, ALIO_IT) is None


# ---------------------------------------------------------------- 고용24 코드·이름과 함께
def test_alio_major_name_is_not_a_work24_code(config):
    """잡알리오 공고의 job.major는 NCS 대분류 이름이다. 예전에는 고용24 코드로 비교해 늘 0이었다."""
    persona1 = DesiredJob(work24_code="D0101", ncs_code=NCS_DATA, name="데이터 분석")
    assert value(config, ALIO_IT, persona1) == config.match.job_match_levels.same_major_category_only


def test_highest_of_work24_and_ncs(config):
    levels = config.match.job_match_levels
    desired = DesiredJob(work24_code="D0101", ncs_code=NCS_DATA, name="x")
    both = Job(code="D0102", middle="D01", major="D", name="데이터 엔지니어", ncs_codes=["20010105"])
    assert value(config, both, desired) == levels.exact  # 고용24는 중분류, NCS는 세분류
    work24_better = Job(code="D0101", middle="D01", major="D", name="데이터 분석가", ncs_codes=["R600020"])
    assert ranking.job_match_detail(config, BasicProfile(desired_jobs=[desired]), work24_better) \
        == (levels.exact, ranking.BASIS_WORK24)
    assert ranking.job_match_detail(config, BasicProfile(desired_jobs=[desired]), both) \
        == (levels.exact, ranking.BASIS_NCS)


def test_name_hit_on_category_name_is_only_major_level(config):
    """공고 이름이 NCS 대분류 이름뿐이면 이름이 겹쳐도 "같은 직종"이 아니라 같은 분야다."""
    levels = config.match.job_match_levels
    profile = BasicProfile(desired_jobs=[DesiredJob(name="회계")])
    assert ranking.job_match_detail(config, profile, ALIO_OFFICE) \
        == (levels.same_major_category_only, ranking.BASIS_NCS_MAJOR_NAME)
    specific = Job(name="회계 사무원", ncs_codes=["02030201"])  # 8자리 NCS가 있으면 이름 그대로
    assert ranking.job_match_value(config, profile, specific) == levels.exact


# ---------------------------------------------------------------- 근거 사실
def test_job_fact_names_the_ncs_level(config):
    levels = config.match.job_match_levels
    assert facts.job_fact(config, levels.same_major, basis=ranking.BASIS_NCS) == facts.FACT_JOB_NCS_MAJOR
    assert facts.job_fact(config, levels.same_major, basis=ranking.BASIS_NCS_MAJOR_NAME) == facts.FACT_JOB_NCS_MAJOR
    assert facts.job_fact(config, levels.same_middle, basis=ranking.BASIS_NCS) == facts.FACT_JOB_NCS_MIDDLE
    assert facts.job_fact(config, levels.exact, basis=ranking.BASIS_NCS) == facts.FACT_JOB_NCS_EXACT
    assert facts.job_fact(config, levels.exact, basis=ranking.BASIS_WORK24) == facts.FACT_JOB_EXACT
    assert facts.job_fact(config, levels.exact) == facts.FACT_JOB_EXACT  # basis 없이 부르던 곳은 그대로
    assert facts.job_fact(config, 0, basis=ranking.BASIS_NCS) is None
    assert "직종" not in facts.FACT_JOB_NCS_MAJOR


def test_feed_card_says_same_field_not_same_job(deps, as_of):
    add_posting(deps, "alio-T-NCS-IT")
    card = next(c for c in ranking.search_postings(deps, "demo1", as_of=as_of, limit=100).items
                if c.job_posting_id == "alio-T-NCS-IT")
    assert card.facts[0] == facts.FACT_JOB_NCS_MAJOR
    assert facts.FACT_JOB_EXACT not in card.facts


@pytest.mark.parametrize("job,expected", [(ALIO_IT, "same_major_category_only"), (ALIO_OFFICE, None)])
def test_match_score_uses_ncs(deps, job, expected):
    cfg = deps.config
    latest = add_posting(deps, "alio-T-SCORE", job=job)
    profile = deps.users.get_basic_profile("demo1")
    breakdown = ranking.match_score(cfg, profile, latest, content_similarity=0.7)
    if expected:
        assert breakdown.job_match == getattr(cfg.match.job_match_levels, expected)
        assert breakdown.job_basis == ranking.BASIS_NCS_MAJOR
    else:
        assert breakdown.job_match == 0  # 비교는 했고 맞는 분류가 없다
