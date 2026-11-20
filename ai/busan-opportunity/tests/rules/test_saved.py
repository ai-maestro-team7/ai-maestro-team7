"""저장·목표 담기(B-09)와 설정(B-07). T-09, T-16, 페르소나 ③."""

import pytest

from opportunity.core import clock, preferences, saved
from opportunity.models import (
    LeaveReason,
    NotificationPrefs,
    OppError,
    PreferencesUpdate,
    SavedKind,
    SaveRequest,
    Sort,
    WorkspaceStatus,
)
from opportunity.notify import scheduler
from opportunity.seeds import demo_world as w


def save(deps, user_id, job_posting_id, kind=SavedKind.INTEREST, *, as_of=w.DEMO_AS_OF, key=None, **extra):
    return saved.add_target_posting(deps, user_id, SaveRequest(job_posting_id=job_posting_id, kind=kind, **extra),
                                    idempotency_key=key, as_of=as_of)


# ---------------------------------------------------------------- 저장
def test_save_interest_writes_saved_and_workspace_together(deps):
    result = save(deps, "demo1", w.BUSAN_DATA)
    assert result.created and result.schedules == []
    assert result.saved.status == WorkspaceStatus.INTEREST and result.saved.is_busan
    assert result.saved.workspace_id == deps.workspaces.workspace_id(w.BUSAN_DATA)
    item = deps.users.get_saved("demo1", w.BUSAN_DATA)
    assert item.snapshot_id == deps.catalog.get_latest(w.BUSAN_DATA).snapshot_id
    assert item.saved_at == "2026-11-21T10:00:00+09:00" and item.job_major == "D"
    assert "status" not in item.to_api()  # 상태는 워크스페이스에만 둔다 (D-36)
    assert deps.users.workspace_txs == [{"Put": {"workspaceId": f"ws-{w.BUSAN_DATA}", "snapshotId": item.snapshot_id,
                                                 "status": "INTEREST"}}]


def test_save_target_status_is_planned(deps):
    result = save(deps, "demo1", w.BUSAN_DATA, SavedKind.TARGET)
    assert result.saved.status == WorkspaceStatus.PLANNED
    ws_id = deps.workspaces.workspace_id(w.BUSAN_DATA)
    assert deps.workspaces.get_status("demo1", ws_id) == "PLANNED"


def test_save_unknown_posting_is_404(deps):
    with pytest.raises(OppError) as e:
        save(deps, "demo1", "wk24-NOPE", key="k1")
    assert e.value.status == 404 and e.value.code == "POSTING_NOT_FOUND"
    assert deps.users.idem == {}  # 실패한 요청은 멱등 기록을 남기지 않는다


def test_save_id_with_hash_is_400(deps):
    with pytest.raises(OppError) as e:
        save(deps, "demo1", "wk24#1")
    assert e.value.status == 400 and e.value.code == "INVALID_INPUT"


def test_saving_twice_returns_current_state(deps):
    save(deps, "demo1", w.BUSAN_DATA, SavedKind.TARGET)
    deps.workspaces.set_status("demo1", deps.workspaces.workspace_id(w.BUSAN_DATA), "APPLIED")
    again = save(deps, "demo1", w.BUSAN_DATA, SavedKind.INTEREST)
    assert again.created is False and again.saved.status == WorkspaceStatus.APPLIED
    assert again.saved.kind == SavedKind.TARGET and again.schedules == []
    assert deps.events.names().count("SAVED") == 1


def test_saved_event_has_no_user_id(deps):
    save(deps, "demo1", w.BUSAN_DATA_PUBLIC, from_alternative_of=w.SEOUL_DATA)
    name, dims = deps.events.events[-1]
    assert name == "SAVED"
    assert dims == {"isBusan": True, "kind": "INTEREST", "fromAlternative": True}
    assert "demo1" not in str(dims)


# ---------------------------------------------------------------- 이유 질문 (T-09)
def test_t09_second_capital_save_does_not_ask_again(deps):
    assert save(deps, "demo1", w.BUSAN_DATA).ask_leave_reason is False  # 부산 공고는 묻지 않고 기회도 쓰지 않는다
    assert save(deps, "demo1", w.SEOUL_DATA).ask_leave_reason is True    # 페르소나 ①
    assert save(deps, "demo1", w.SEOUL_DATA_HYBRID).ask_leave_reason is False
    assert deps.users.get_prefs("demo1").leave_reason_asked_at == "2026-11-21T10:00:00+09:00"


def test_t09_reason_already_chosen_is_not_asked(deps):
    preferences.set_preferences(deps, "demo1", PreferencesUpdate(leave_reason=LeaveReason.SALARY))
    assert save(deps, "demo1", w.SEOUL_DATA).ask_leave_reason is False


def test_t09_unknown_region_is_not_capital(deps):
    assert save(deps, "demo1", w.DATA_UNKNOWN_REGION).ask_leave_reason is False


# ---------------------------------------------------------------- 멱등 (T-16)
def test_t16_same_key_twice_applies_once(deps):
    first = save(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, SavedKind.TARGET, key="idem-1")
    second = save(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, SavedKind.TARGET, key="idem-1")
    assert second == first and second.created is True  # 저장된 결과를 그대로 돌려준다
    assert len(deps.users.list_saved("demo3")) == 1
    assert len(deps.users.workspace_txs) == 1
    assert deps.events.names().count("SAVED") == 1
    assert len(deps.scheduler.schedules) == 2


def test_t16_same_key_different_body_is_409(deps):
    save(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, SavedKind.TARGET, key="idem-1")
    with pytest.raises(OppError) as e:
        save(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, SavedKind.INTEREST, key="idem-1")
    assert e.value.status == 409 and e.value.code == "PRECONDITION_NOT_MET"
    with pytest.raises(OppError):
        save(deps, "demo3", w.BUSAN_ADMIN_PUBLIC, key="idem-1")
    assert len(deps.users.list_saved("demo3")) == 1


def test_t16_keys_are_per_user(deps):
    save(deps, "demo1", w.BUSAN_DATA, key="same")
    other = save(deps, "demo2", w.BUSAN_ACCOUNT, key="same")
    assert other.created and other.saved.job_posting_id == w.BUSAN_ACCOUNT


# ---------------------------------------------------------------- 마감 일정 (페르소나 ③)
def test_persona3_target_creates_d7_d3_schedules(deps):
    result = save(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, SavedKind.TARGET)  # 마감 2026-12-08
    assert [(s.type, s.at, s.label) for s in result.schedules] == [
        ("TARGET_DEADLINE", "2026-12-01T09:00:00+09:00", "마감 D-7"),
        ("TARGET_DEADLINE", "2026-12-05T09:00:00+09:00", "마감 D-3"),
    ]
    item = deps.users.get_saved("demo3", w.BUSAN_FINANCE_PUBLIC)
    assert sorted(item.schedule_names) == sorted(deps.scheduler.schedules)
    payloads = [payload for _, payload in deps.scheduler.schedules.values()]
    assert {p["check"] for p in payloads} == {7, 3}
    assert all(p == {"userId": "demo3", "type": "TARGET_DEADLINE", "targetId": w.BUSAN_FINANCE_PUBLIC,
                     "check": p["check"]} for p in payloads)


def test_mock_example_schedule_times(deps):
    """개발계획서2 §5.7 예시와 같은 시각 (마감 11-30 → 11-23, 11-27 09:00)."""
    result = save(deps, "demo1", w.BUSAN_DATA_PUBLIC, SavedKind.TARGET)
    assert [s.at for s in result.schedules] == ["2026-11-23T09:00:00+09:00", "2026-11-27T09:00:00+09:00"]


def test_rolling_posting_has_no_schedule(deps):
    result = save(deps, "demo2", w.BUSAN_ACCOUNT_GANGSO, SavedKind.TARGET)
    assert result.created and result.schedules == [] and deps.scheduler.schedules == {}


def test_past_dates_are_not_scheduled(deps):
    result = save(deps, "demo1", w.BUSAN_DATA_PUBLIC, SavedKind.TARGET, as_of="2026-11-25T10:00:00+09:00")
    assert [s.label for s in result.schedules] == ["마감 D-3"]
    late = save(deps, "demo2", w.BUSAN_DATA_PUBLIC, SavedKind.TARGET, as_of="2026-11-28T10:00:00+09:00")
    assert late.schedules == [] and deps.users.get_saved("demo2", w.BUSAN_DATA_PUBLIC).schedule_names == []


def test_expired_posting_has_no_schedule(deps):
    assert save(deps, "demo1", w.BUSAN_DATA_EXPIRED, SavedKind.TARGET).schedules == []


def test_schedule_name_is_hashed_and_short():
    name = scheduler.schedule_name("demo1", "TARGET_DEADLINE", "wk24-K000000000000000000000002", "d7")
    assert name.startswith("team07-opp-") and len(name) <= 64
    assert "demo1" not in name and "#" not in name
    assert name == scheduler.schedule_name("demo1", "TARGET_DEADLINE", "wk24-K000000000000000000000002", "d7")
    assert name != scheduler.schedule_name("demo2", "TARGET_DEADLINE", "wk24-K000000000000000000000002", "d7")
    assert name != scheduler.schedule_name("demo1", "TARGET_DEADLINE", "wk24-K000000000000000000000002", "d3")


def test_existing_schedule_is_not_an_error(deps):
    latest = deps.catalog.get_latest(w.BUSAN_DATA)
    as_of = clock.parse_as_of(w.DEMO_AS_OF)
    first = scheduler.schedule_target_deadlines(deps, "demo1", latest, as_of=as_of)
    second = scheduler.schedule_target_deadlines(deps, "demo1", latest, as_of=as_of)
    assert first == second and len(deps.scheduler.schedules) == 2


# ---------------------------------------------------------------- 저장 목록
def test_list_saved_reads_status_from_workspace(deps):
    save(deps, "demo1", w.BUSAN_DATA, as_of="2026-11-21T10:00:00+09:00")
    save(deps, "demo1", w.SEOUL_DATA, SavedKind.TARGET, as_of="2026-11-21T11:00:00+09:00")
    deps.workspaces.set_status("demo1", deps.workspaces.workspace_id(w.BUSAN_DATA), "PREPARING")
    items = saved.list_saved(deps, "demo1").items
    assert [i.job_posting_id for i in items] == [w.SEOUL_DATA, w.BUSAN_DATA]  # 최근 저장 먼저
    assert [i.status for i in items] == [WorkspaceStatus.PLANNED, WorkspaceStatus.PREPARING]
    assert items[1].title == "데이터 분석 신입" and items[1].closes_at == "2026-12-05"
    assert saved.list_saved(deps, "demo2").items == []


# ---------------------------------------------------------------- 설정 (B-07)
def test_get_preferences_defaults(deps):
    view = preferences.get_preferences(deps, "demo1")
    assert view.sort == Sort.BUSAN_FIRST and view.leave_reason is None
    assert view.notifications == NotificationPrefs() and view.receiving_policies == []


def test_set_preferences_changes_only_sent_fields(deps):
    preferences.set_preferences(deps, "demo1", PreferencesUpdate(leave_reason=LeaveReason.GROWTH,
                                                                 receiving_policies=["청년내일저축계좌"]))
    view = preferences.set_preferences(deps, "demo1",
                                       PreferencesUpdate.model_validate({"notifications": {"email": True}}))
    assert view.leave_reason == LeaveReason.GROWTH and view.receiving_policies == ["청년내일저축계좌"]
    assert view.notifications.email is True and view.sort == Sort.BUSAN_FIRST
    assert deps.users.get_prefs("demo1").leave_reason_asked_at  # 직접 고르면 다시 묻지 않는다
    cleared = preferences.set_preferences(deps, "demo1", PreferencesUpdate.model_validate({"leaveReason": None}))
    assert cleared.leave_reason is None and cleared.notifications.email is True


def test_busan_first_off_event(deps):
    preferences.set_preferences(deps, "demo1", PreferencesUpdate(sort=Sort.BUSAN_FIRST))
    assert "BUSAN_FIRST_OFF" not in deps.events.names()
    preferences.set_preferences(deps, "demo1", PreferencesUpdate(sort=Sort.MATCH))
    assert deps.events.events == [("BUSAN_FIRST_OFF", {"sort": "MATCH"})]
    preferences.set_preferences(deps, "demo1", PreferencesUpdate(sort=Sort.DEADLINE))
    assert deps.events.names().count("BUSAN_FIRST_OFF") == 1
