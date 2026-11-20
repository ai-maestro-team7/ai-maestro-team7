"""0단계 계약 확인: 설정 검사, 시계, 메모리 저장소, 데모 데이터."""

import copy
import json

import pytest

from opportunity import config as config_module
from opportunity.config import ConfigError, parse_config
from opportunity.core import clock, copy_rules, eligibility
from opportunity.core.texts import posting_text, profile_text
from opportunity.models import (
    Badge,
    EligibilityStatus,
    Notification,
    NotificationType,
    PolicyAlert,
    PostingCard,
    SavedItem,
    SavedKind,
)
from opportunity.seeds import demo_world as w
from opportunity.store.memory import cosine


def raw_config():
    return json.loads(config_module.DEFAULT_PATH.read_text(encoding="utf-8"))


def test_default_config_loads(config):
    assert config.ranking.busan_boost == 0.06
    assert config.ranking.busan_boost < config.ranking.inversion_guard
    assert config.compare.rent_conversion_rate is None


def test_t03_boost_not_below_guard_fails():
    raw = raw_config()
    raw["ranking"]["busanBoost"] = raw["ranking"]["inversionGuard"]
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_weights_must_sum_to_one():
    raw = raw_config()
    raw["match"]["weights"]["jobMatch"] = 0.5
    with pytest.raises(ConfigError):
        parse_config(raw)
    raw = raw_config()
    raw["alternatives"]["weights"]["reason"] = 0.5
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_threshold_out_of_range_fails():
    raw = raw_config()
    raw["alternatives"]["minSimilarity"] = 1.2
    with pytest.raises(ConfigError):
        parse_config(raw)


def test_require_env_names_the_variable(monkeypatch):
    monkeypatch.delenv("MODEL_ID", raising=False)
    with pytest.raises(ConfigError, match="MODEL_ID"):
        config_module.require_env("MODEL_ID")


def test_clock(as_of):
    assert clock.day(as_of) == "2026-11-21"
    assert clock.iso(clock.parse_as_of("2026-11-21")) == "2026-11-21T09:00:00+09:00"
    assert clock.d_day("2026-11-30", as_of) == 9
    assert clock.d_day("9999-12-31", as_of) is None
    assert clock.is_expired("2026-11-20", as_of) and not clock.is_expired("2026-11-21", as_of)
    assert not clock.is_expired("9999-12-31", as_of)
    assert clock.age_range(2003, as_of) == (22, 23)
    assert clock.week_key(as_of) == "2026-W47"
    assert clock.deadline_number("2026-12-05") == 20261205
    assert clock.resolve_as_of(None, "2026-12-01T09:00:00+09:00").day == 1


def test_camel_case_output(deps):
    latest = deps.catalog.get_latest(w.BUSAN_DATA)
    data = latest.to_api()
    assert data["jobPostingId"] == w.BUSAN_DATA and data["isBusan"] is True
    assert data["workRegion"]["sigungu"] == "26350"
    assert "job_posting_id" not in data
    assert PostingCard.model_validate({**data, "matchScore": 0.7, "matchLevel": "GOOD"}).job_posting_id == w.BUSAN_DATA


def test_demo_world_regions(deps):
    latest = deps.catalog.get_latest
    assert latest(w.BUSAN_DATA).is_busan and not latest(w.BUSAN_DATA).is_capital_area
    assert latest(w.SEOUL_DATA).is_capital_area and latest(w.GYEONGGI_DATA_ENG).is_capital_area
    unknown = latest(w.DATA_UNKNOWN_REGION)
    assert not unknown.is_busan and unknown.work_region.unknown  # 본사가 부산이어도 근무지를 모르면 부산이 아니다
    assert latest(w.BUSAN_DATA_EXPIRED).is_expired and not latest(w.BUSAN_DATA_JUST_CLOSED).is_expired
    assert all(p.is_sample for p in deps.catalog.latest.values())


def test_demo_world_snapshot_ids_are_stable():
    first = {s.job_posting_id: s.snapshot_id for s in w.build_snapshots()}
    second = {s.job_posting_id: s.snapshot_id for s in w.build_snapshots()}
    assert first == second
    assert all("#" not in sid for sid in first.values())


def test_demo_world_similarity(deps):
    seoul = deps.vectors.get(w.SEOUL_DATA)
    low = deps.config.alternatives.min_similarity
    assert cosine(seoul, deps.vectors.get(w.BUSAN_DATA)) >= low
    assert cosine(seoul, deps.vectors.get(w.BUSAN_DATA_PUBLIC)) >= low
    assert cosine(deps.vectors.get(w.SEOUL_GAME), deps.vectors.get(w.BUSAN_BACKEND)) < low
    profile_vector = deps.embedder.embed(profile_text(deps.users.get_basic_profile("demo1")), kind="query")
    assert cosine(profile_vector, seoul) >= 0.8


def test_vector_filter(deps):
    query = deps.vectors.get(w.SEOUL_DATA)
    hits = deps.vectors.query(query, top_k=30, filter={"isBusan": True, "active": True,
                                                        "deadline": {"$gte": 20261121}})
    keys = [h.key for h in hits]
    assert w.BUSAN_DATA in keys and w.SEOUL_DATA not in keys
    assert w.BUSAN_DATA_EXPIRED not in keys and w.BUSAN_DATA_JUST_CLOSED not in keys
    assert hits == sorted(hits, key=lambda h: -h.similarity)


def test_catalog_queries(deps):
    busan = deps.catalog.query_postings_by_sido("26", closes_from="2026-11-21")
    assert busan and all(p.is_busan for p in busan)
    assert [p.closes_at for p in busan] == sorted(p.closes_at for p in busan)
    assert {p.policy_id for p in deps.catalog.query_policies("00")} == {w.P_NATIONAL_JOB, w.P_NATIONAL_ASSET}
    assert w.P_BUSAN_NAMGU in {p.policy_id for p in deps.catalog.query_policies("26")}  # 구 단위도 시·도 키에 둔다
    assert deps.catalog.get_policy(w.P_UNVERIFIED).verified is False
    assert deps.catalog.get_alts(w.SEOUL_DATA).candidates[0].job_posting_id == w.BUSAN_DATA
    assert deps.catalog.get_alts(w.GYEONGGI_DATA_ENG) is None


def test_eligibility_contract(deps):
    profile = deps.users.get_basic_profile("demo2")  # 전문대 졸업
    rules = deps.catalog.get_latest(w.BUSAN_DATA).eligibility_rules  # 학사 이상
    result = eligibility.judge(deps, profile, rules)
    assert result.status == EligibilityStatus.INELIGIBLE
    assert eligibility.required_ratio(result, 0.5) == 0.5
    ok = eligibility.judge(deps, deps.users.get_basic_profile("demo1"), rules)
    assert ok.status == EligibilityStatus.ELIGIBLE and eligibility.required_ratio(ok, 0.5) == 1.0
    assert eligibility.required_ratio(eligibility.judge(deps, profile, []), 0.5) is None


def test_user_repo_conditional_writes(deps, as_of):
    users = deps.users
    assert users.mark_leave_reason_asked("demo1", as_of) is True
    assert users.mark_leave_reason_asked("demo1", as_of) is False
    item = SavedItem(job_posting_id=w.SEOUL_DATA, kind=SavedKind.INTEREST, snapshot_id="s", is_busan=False,
                     saved_at=as_of)
    assert users.put_saved("demo1", item, {"Put": {}}) is True and users.put_saved("demo1", item) is False
    assert users.put_alert("demo1", PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at=as_of, schedule_name="n"))
    assert not users.put_alert("demo1", PolicyAlert(policy_id=w.P_JOY_DOUBLE, scheduled_at=as_of, schedule_name="n"))
    for stamp in ("20261121T100000-aaaaaaaa", "20261122T100000-bbbbbbbb"):
        noti = Notification(notification_id=stamp, type=NotificationType.TARGET_DEADLINE, title="t", body="b",
                            created_at=as_of)
        assert users.put_notification("demo1", noti) is True
        assert users.put_notification("demo1", noti) is False
    page, cursor = users.list_notifications("demo1", limit=1)
    assert page[0].notification_id.startswith("20261122") and cursor
    assert users.list_notifications("demo1", cursor=cursor)[0][0].notification_id.startswith("20261121")
    assert [users.incr_immediate_count("demo1", "2026-W47", 2) for _ in range(3)] == [True, True, False]
    assert users.idem_begin("demo1", "k", "h1").state == "NEW"
    users.idem_finish("demo1", "k", {"ok": True})
    assert users.idem_begin("demo1", "k", "h1").result == {"ok": True}
    assert users.idem_begin("demo1", "k", "h2").state == "CONFLICT"


def test_scheduler_and_workspace(deps, as_of):
    at = clock.parse_as_of("2026-11-23T09:00:00+09:00")
    assert deps.scheduler.create_once("n1", at, {"type": "TARGET_DEADLINE"}) is True
    assert deps.scheduler.create_once("n1", at, {}) is False
    assert deps.scheduler.due(clock.parse_as_of(as_of)) == []
    assert len(deps.scheduler.due(clock.parse_as_of("2026-11-24"))) == 1
    assert deps.workspaces.put_tx_item("demo1", w.BUSAN_DATA, "s", "PLANNED") is not None
    assert deps.workspaces.put_tx_item("demo1", w.BUSAN_DATA, "s", "PLANNED") is None
    assert deps.workspaces.get_status("demo1", deps.workspaces.workspace_id(w.BUSAN_DATA)) == "PLANNED"


def test_copy_rules():
    assert copy_rules.find_forbidden("부산을 떠나면 손해예요") == ["떠나면", "손해"]
    assert copy_rules.find_forbidden("지역인재 전형 대상일 수 있어요 · 공고문 확인") == []
    assert copy_rules.numbers_in("연 4,000만 원, 마감 D-3") == {"4000", "3"}
    assert copy_rules.deadline_label(3) == "마감 D-3" and copy_rules.deadline_label(None) == "상시 채용"
    assert copy_rules.salary_label(True, 4000, 4400) == "연 4,000~4,400만 원"
    assert copy_rules.salary_label(False, None, None) == "공고에 없음"


def test_texts(deps):
    snap = deps.catalog.get_snapshot(w.BUSAN_DATA, deps.catalog.get_latest(w.BUSAN_DATA).snapshot_id)
    assert posting_text(snap).startswith("데이터 분석가 | 데이터 분석 신입 | ")
    assert "SQL, Python" in posting_text(snap) and "ADsP" in posting_text(snap)


def test_badge_without_source_is_detectable(deps):
    badges = deps.catalog.get_latest(w.BUSAN_BADGE_NO_SOURCE).badges
    assert badges == [Badge(type="CHEONGKKEUL", label="청끌기업")] and badges[0].source is None


def test_builds_are_independent(deps):
    other = w.build_deps(copy.deepcopy(deps.config))
    other.catalog.latest.clear()
    assert deps.catalog.get_latest(w.BUSAN_DATA) is not None
