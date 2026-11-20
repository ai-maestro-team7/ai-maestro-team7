"""알림(B-10). T-10, T-11, 조용한 시간, 정책 열리면 알림, 데모 시간 앞당기기."""

import re

import pytest

from opportunity.core import clock, saved
from opportunity.models import NotificationPrefs, OppError, OppPrefs, SavedKind, SaveRequest
from opportunity.notify import notifier, scheduler
from opportunity.seeds import demo_world as w


def target(deps, user_id, job_posting_id, as_of=w.DEMO_AS_OF):
    return saved.add_target_posting(deps, user_id, SaveRequest(job_posting_id=job_posting_id, kind=SavedKind.TARGET),
                                    as_of=as_of)


def payload(user_id, job_posting_id, check=7):
    return {"userId": user_id, "type": "TARGET_DEADLINE", "targetId": job_posting_id, "check": check}


def notifications(deps, user_id):
    return deps.users.list_notifications(user_id, limit=100)[0]


# ---------------------------------------------------------------- 목표 공고 마감
def test_target_deadline_notifies_with_label(deps):
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    assert notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-01T09:00:00+09:00")
    [noti] = notifications(deps, "demo3")
    assert noti.type == "TARGET_DEADLINE" and noti.title == "목표 공고 마감 D-7"
    assert noti.body == "가상주택금융공사 · 일반행정·금융 신입 채용"
    assert noti.link == f"/opportunities/postings/{w.BUSAN_FINANCE_PUBLIC}"
    assert noti.created_at == "2026-12-01T09:00:00+09:00" and noti.simulated is False
    assert re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{8}", noti.notification_id)
    assert "#" not in noti.notification_id


def test_target_deadline_skips_unsaved_closed_or_applied(deps):
    assert not notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-01T09:00")
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    assert not notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-09T09:00")
    deps.workspaces.set_status("demo3", deps.workspaces.workspace_id(w.BUSAN_FINANCE_PUBLIC), "APPLIED")
    assert not notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-01T09:00")
    assert notifications(deps, "demo3") == []


def test_unknown_payload_is_ignored(deps):
    assert notifier.handle_schedule(deps, {"userId": "demo1", "type": "WHAT", "targetId": "x"}) is False
    assert notifier.handle_schedule(deps, {"type": "TARGET_DEADLINE", "targetId": "x"}) is False


# ---------------------------------------------------------------- 중복 (T-10)
def test_t10_same_notification_twice_is_stored_and_sent_once(deps):
    deps.users.put_prefs("demo3", OppPrefs(notifications=NotificationPrefs(email=True)))
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    p = payload("demo3", w.BUSAN_FINANCE_PUBLIC)
    assert notifier.handle_schedule(deps, p, as_of="2026-12-01T09:00:00+09:00") is True
    assert notifier.handle_schedule(deps, p, as_of="2026-12-01T09:00:05+09:00") is False  # 재전송
    assert len(notifications(deps, "demo3")) == 1
    assert len(deps.mailer.sent) == 1 and deps.mailer.sent[0][1] == "목표 공고 마감 D-7"


def test_mail_only_with_consent(deps):
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    assert notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-01T09:00")
    assert deps.mailer.sent == []
    deps.mailer = None
    deps.users.put_prefs("demo3", OppPrefs(notifications=NotificationPrefs(email=True)))
    assert notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC, 3), as_of="2026-12-05T09:00")
    assert len(notifications(deps, "demo3")) == 2  # 메일 구현이 없어도 알림함에는 남는다


# ---------------------------------------------------------------- 즉시 알림 한도 (T-11)
def test_t11_third_immediate_in_a_week_goes_to_next_digest(deps):
    ids = [w.BUSAN_DATA, w.BUSAN_ACCOUNT, w.BUSAN_FINANCE_PUBLIC]
    for pid in ids:
        target(deps, "demo1", pid)
    deps.scheduler.schedules.clear()
    at = "2026-12-01T09:00:00+09:00"  # 2026-W49
    results = [notifier.handle_schedule(deps, payload("demo1", pid), as_of=at) for pid in ids]
    assert results == [True, True, False]
    assert len(notifications(deps, "demo1")) == 2
    [(name, (when, deferred))] = deps.scheduler.schedules.items()
    assert name.startswith("team07-opp-") and clock.iso(when) == "2026-12-02T09:00:00+09:00"
    assert deferred == {**payload("demo1", w.BUSAN_FINANCE_PUBLIC), "digest": True}
    # 다음 날 요약은 즉시 알림 한도에 세지 않는다
    assert notifier.handle_schedule(deps, deferred, as_of=when) is True
    assert notifications(deps, "demo1")[0].title == "목표 공고 마감 D-6"


def test_cap_resets_next_week(deps):
    for pid in (w.BUSAN_DATA, w.BUSAN_ACCOUNT, w.BUSAN_FINANCE_PUBLIC):
        target(deps, "demo1", pid)
    for pid in (w.BUSAN_DATA, w.BUSAN_ACCOUNT):
        assert notifier.handle_schedule(deps, payload("demo1", pid), as_of="2026-11-27T09:00")  # W48
    assert notifier.handle_schedule(deps, payload("demo1", w.BUSAN_FINANCE_PUBLIC), as_of="2026-12-01T09:00")


# ---------------------------------------------------------------- 조용한 시간
@pytest.mark.parametrize("at, expected", [("2026-12-01T23:00:00+09:00", "2026-12-02T09:00:00+09:00"),
                                          ("2026-12-02T03:00:00+09:00", "2026-12-02T09:00:00+09:00")])
def test_quiet_hours_defer_to_next_digest(deps, at, expected):
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    deps.scheduler.schedules.clear()
    assert notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC), as_of=at) is False
    assert notifications(deps, "demo3") == []
    [(when, deferred)] = deps.scheduler.schedules.values()
    assert clock.iso(when) == expected and "digest" in deferred
    assert deps.users.caps == {}  # 미룬 알림은 한도를 쓰지 않는다


def test_quiet_hours_bounds(deps):
    assert notifier.is_quiet(deps, clock.parse_as_of("2026-12-01T22:00"))
    assert notifier.is_quiet(deps, clock.parse_as_of("2026-12-01T07:59"))
    assert not notifier.is_quiet(deps, clock.parse_as_of("2026-12-01T08:00"))
    assert not notifier.is_quiet(deps, clock.parse_as_of("2026-12-01T21:59"))


# ---------------------------------------------------------------- 정책 열리면 알림
def test_policy_alert_uses_last_cycle_plus_one_year(deps):
    result = scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, as_of=w.DEMO_AS_OF)
    assert result.created and result.alert.scheduled_at == "2027-08-10T09:00:00+09:00"
    alert = deps.users.get_alert("demo1", w.P_JOY_DOUBLE)
    assert deps.scheduler.schedules[alert.schedule_name][1] == {
        "userId": "demo1", "type": "POLICY_OPEN", "targetId": w.P_JOY_DOUBLE, "check": 0}
    again = scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, as_of=w.DEMO_AS_OF)
    assert again.created is False and again.alert == result.alert


def test_policy_alert_without_cycle_rechecks_later(deps):
    result = scheduler.subscribe_policy_alert(deps, "demo1", w.P_STAY_LOAN, as_of=w.DEMO_AS_OF)
    assert result.alert.scheduled_at == "2026-11-28T09:00:00+09:00"  # recheckDays(7) 뒤


def test_policy_alert_hidden_policy_is_404(deps):
    for pid in (w.P_UNVERIFIED, "seed-nope"):
        with pytest.raises(OppError) as e:
            scheduler.subscribe_policy_alert(deps, "demo1", pid, idempotency_key="k")
        assert e.value.code == "POLICY_NOT_FOUND"
    assert deps.users.idem == {}


def test_policy_alert_idempotency_key(deps):
    first = scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, idempotency_key="a1", as_of=w.DEMO_AS_OF)
    assert scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, idempotency_key="a1") == first
    with pytest.raises(OppError) as e:
        scheduler.subscribe_policy_alert(deps, "demo1", w.P_MOVING, idempotency_key="a1")
    assert e.value.status == 409


def test_policy_not_open_rechecks_until_max(deps):
    scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, as_of=w.DEMO_AS_OF)
    p = {"userId": "demo1", "type": "POLICY_OPEN", "targetId": w.P_JOY_DOUBLE, "check": 0}
    assert notifier.handle_schedule(deps, p, as_of="2027-08-10T09:00:00+09:00") is False  # 작년 일정만 있음
    alert = deps.users.get_alert("demo1", w.P_JOY_DOUBLE)
    assert alert.checks == 1 and alert.scheduled_at == "2027-08-17T09:00:00+09:00"
    assert deps.scheduler.schedules[alert.schedule_name][1]["check"] == 1
    max_rechecks = deps.config.notifications.max_rechecks
    for _ in range(max_rechecks + 2):
        current = deps.users.get_alert("demo1", w.P_JOY_DOUBLE)
        notifier.handle_schedule(deps, {**p, "check": current.checks}, as_of=current.scheduled_at)
    assert deps.users.get_alert("demo1", w.P_JOY_DOUBLE).checks == max_rechecks
    assert notifications(deps, "demo1") == []


def test_policy_open_notifies_once_and_clears_alert(deps):
    scheduler.subscribe_policy_alert(deps, "demo1", w.P_JOY_DOUBLE, as_of=w.DEMO_AS_OF)
    policy = deps.catalog.get_policy(w.P_JOY_DOUBLE)
    deps.catalog.put_policy(policy.model_copy(update={"apply_start": "2027-08-09", "apply_end": "2027-08-20"}))
    p = {"userId": "demo1", "type": "POLICY_OPEN", "targetId": w.P_JOY_DOUBLE, "check": 0}
    assert notifier.handle_schedule(deps, p, as_of="2027-08-10T09:00:00+09:00") is True
    [noti] = notifications(deps, "demo1")
    assert noti.type == "POLICY_OPEN" and noti.link == f"/opportunities/policies/{w.P_JOY_DOUBLE}"
    assert "2027-08-09~2027-08-20" in noti.body
    assert deps.users.get_alert("demo1", w.P_JOY_DOUBLE) is None
    assert notifier.handle_schedule(deps, p, as_of="2027-08-10T09:00:00+09:00") is False


# ---------------------------------------------------------------- 알림함
def test_inbox_newest_first_and_mark_read(deps):
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC)
    notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC, 7), as_of="2026-12-01T09:00")
    notifier.handle_schedule(deps, payload("demo3", w.BUSAN_FINANCE_PUBLIC, 3), as_of="2026-12-05T09:00")
    page = notifier.check_new_opportunities(deps, "demo3", limit=1)
    assert page.items[0].title == "목표 공고 마감 D-3" and page.next_cursor
    rest = notifier.check_new_opportunities(deps, "demo3", cursor=page.next_cursor)
    assert [n.title for n in rest.items] == ["목표 공고 마감 D-7"] and rest.next_cursor is None
    assert notifier.mark_read(deps, "demo3", page.items[0].notification_id) is True
    assert notifier.check_new_opportunities(deps, "demo3").items[0].read is True
    assert notifier.mark_read(deps, "demo3", "20261201T090000-00000000") is False
    assert notifier.mark_read(deps, "demo1", page.items[0].notification_id) is False  # 남의 알림


# ---------------------------------------------------------------- 데모 시간 앞당기기
def test_demo_clock_fires_due_schedules_as_simulated(deps):
    assert notifier.advance_demo_clock(deps, "demo3", w.DEMO_AS_OF).fired == 0
    target(deps, "demo3", w.BUSAN_FINANCE_PUBLIC, as_of=None)  # demoAsOf 기준으로 저장
    assert deps.users.get_saved("demo3", w.BUSAN_FINANCE_PUBLIC).saved_at == "2026-11-21T10:00:00+09:00"

    first = notifier.advance_demo_clock(deps, "demo3", "2026-12-02T09:00:00+09:00")
    assert first.fired == 1 and first.simulated and first.as_of == "2026-12-02T09:00:00+09:00"
    assert deps.users.get_prefs("demo3").demo_as_of == "2026-12-02T09:00:00+09:00"
    second = notifier.advance_demo_clock(deps, "demo3", "2026-12-05T09:00:00+09:00")
    assert second.fired == 1
    items = notifications(deps, "demo3")
    assert [n.title for n in items] == ["목표 공고 마감 D-3", "목표 공고 마감 D-7"]
    assert all(n.simulated for n in items)
    assert [n.created_at for n in items] == ["2026-12-05T09:00:00+09:00", "2026-12-01T09:00:00+09:00"]
    assert deps.scheduler.schedules == {}  # 실행한 일정은 지운다
    assert notifier.advance_demo_clock(deps, "demo3", "2026-12-06T09:00:00+09:00").fired == 0


def test_demo_clock_runs_policy_alerts_and_rechecks(deps):
    notifier.advance_demo_clock(deps, "demo1", w.DEMO_AS_OF)
    scheduler.subscribe_policy_alert(deps, "demo1", w.P_BUSAN_INTERVIEW)  # 상시. 11-28 09:00 확인
    scheduler.subscribe_policy_alert(deps, "demo1", w.P_DIDIMDOL)         # 2027-03-02 09:00. 작년 일정만 있음
    result = notifier.advance_demo_clock(deps, "demo1", "2027-04-30T09:00:00+09:00")
    assert result.fired == 1
    [noti] = notifications(deps, "demo1")
    assert noti.type == "POLICY_OPEN" and noti.simulated
    alert = deps.users.get_alert("demo1", w.P_DIDIMDOL)
    assert alert.checks == deps.config.notifications.max_rechecks  # 재확인을 다 쓰고 멈춤
    assert notifier.advance_demo_clock(deps, "demo1", "2027-05-30T09:00:00+09:00").fired == 0


def test_demo_clock_only_touches_this_user(deps):
    for user in ("demo1", "demo3"):
        notifier.advance_demo_clock(deps, user, w.DEMO_AS_OF)
        target(deps, user, w.BUSAN_FINANCE_PUBLIC, as_of=None)
    notifier.advance_demo_clock(deps, "demo3", "2026-12-05T09:00:00+09:00")
    assert len(notifications(deps, "demo3")) == 2 and notifications(deps, "demo1") == []
    assert len(deps.scheduler.schedules) == 2  # demo1 일정은 그대로
