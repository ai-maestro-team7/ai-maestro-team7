"""일정이 울렸을 때 처리와 알림함.

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-10. 테스트: T-10, T-11.
"""

import hashlib
from datetime import date, datetime
from enum import StrEnum

from ..core import clock
from ..core.copy_rules import deadline_label
from ..deps import Deps
from ..models.api import DemoClockResponse, NotificationsResponse
from ..models.enums import NotificationType, SavedKind, WorkspaceStatus
from ..models.policy import Policy
from ..models.user_state import Notification, PolicyAlert
from . import scheduler

DONE_STATUSES = {WorkspaceStatus.APPLIED, WorkspaceStatus.RESULT, WorkspaceStatus.CLOSED}  # 마감 알림이 필요 없다


class Delivery(StrEnum):
    SENT = "SENT"
    DEFERRED = "DEFERRED"    # 조용한 시간이거나 즉시 알림 한도를 넘어 다음 요약으로 미룸
    DUPLICATE = "DUPLICATE"  # 같은 알림이 이미 있음 (T-10)


# ---------------------------------------------------------------- 알림 ID와 시간
def notification_id(deps: Deps, user_id: str, kind: str, target_id: str, as_of: datetime) -> str:
    """`{yyyyMMddTHHmmss}-{해시 8자}`. 해시는 sha256(userId·종류·대상·날짜)다.

    시각 부분은 그날의 요약 시각(digestHour)으로 고정한다. 같은 날 같은 알림이 다시 오면 ID가 같아
    조건부 쓰기에서 걸린다. 실제 만든 시각은 createdAt에 둔다.
    """
    day = clock.day(as_of)
    digest = hashlib.sha256(f"{user_id}|{kind}|{target_id}|{day}".encode()).hexdigest()[:8]
    stamp = clock.at_hour(day, deps.config.notifications.digest_hour).strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{digest}"


def is_quiet(deps: Deps, at: datetime) -> bool:
    """quietHours [시작, 끝)에는 보내지 않는다. [22, 8]이면 22시~다음 날 8시."""
    start, end = deps.config.notifications.quiet_hours
    hour = clock.parse_as_of(at).hour
    return (hour >= start or hour < end) if start > end else start <= hour < end


def _defer(deps: Deps, payload: dict, at: datetime, *, digest: bool) -> None:
    user_id, kind, target = payload["userId"], payload["type"], payload["targetId"]
    name = scheduler.schedule_name(user_id, kind, target, f"defer-{at.strftime('%Y%m%dT%H')}")
    deps.scheduler.create_once(name, at, {**payload, "digest": digest or bool(payload.get("digest"))})


def _deliver(deps: Deps, payload: dict, *, title: str, body: str, link: str, as_of: datetime,
             simulated: bool) -> Delivery:
    user_id, kind, target = payload["userId"], payload["type"], payload["targetId"]
    if is_quiet(deps, as_of):
        _defer(deps, payload, scheduler.next_digest(deps, as_of), digest=False)
        return Delivery.DEFERRED
    cap = deps.config.notifications.immediate_per_week
    if not payload.get("digest") and not deps.users.incr_immediate_count(user_id, clock.week_key(as_of), cap):
        _defer(deps, payload, scheduler.next_digest(deps, as_of, days=1), digest=True)  # 다음 날 요약 (T-11)
        return Delivery.DEFERRED
    notification = Notification(notification_id=notification_id(deps, user_id, kind, target, as_of),
                                type=NotificationType(kind), title=title, body=body, link=link,
                                created_at=clock.iso(as_of), simulated=simulated)
    if not deps.users.put_notification(user_id, notification):
        return Delivery.DUPLICATE
    if deps.mailer is not None and deps.users.get_prefs(user_id).notifications.email:
        deps.mailer.send(user_id, title, f"{body}\n{link}")
    return Delivery.SENT


# ---------------------------------------------------------------- 종류별 처리
def _target_deadline(deps: Deps, payload: dict, as_of: datetime, simulated: bool) -> bool:
    user_id, job_posting_id = payload["userId"], payload["targetId"]
    saved = deps.users.get_saved(user_id, job_posting_id)
    if saved is None or saved.kind != SavedKind.TARGET:
        return False
    posting = deps.catalog.get_latest(job_posting_id)
    if posting is None or posting.is_expired or clock.is_expired(posting.closes_at, as_of):
        return False
    workspace_id = saved.workspace_id or deps.workspaces.workspace_id(job_posting_id)
    if deps.workspaces.get_status(user_id, workspace_id) in DONE_STATUSES:
        return False
    label = deadline_label(clock.d_day(posting.closes_at, as_of))
    result = _deliver(deps, payload, title=f"목표 공고 {label}", body=f"{posting.organization} · {posting.title}",
                      link=f"/opportunities/postings/{job_posting_id}", as_of=as_of, simulated=simulated)
    return result == Delivery.SENT


def _is_open(policy: Policy, as_of: datetime) -> bool:
    today = clock.day(as_of)
    return (policy.apply_start is None or policy.apply_start <= today) and today <= policy.apply_end


def _policy_body(policy: Policy) -> str:
    parts = [policy.summary] if policy.summary else []
    if policy.apply_start and not clock.is_rolling(policy.apply_end):
        parts.append(f"신청 기간 {policy.apply_start}~{policy.apply_end}")
    return " · ".join(parts) or "신청 조건과 기간을 원문에서 확인해 주세요"


def _recheck(deps: Deps, user_id: str, alert: PolicyAlert, as_of: datetime) -> None:
    """아직 열리지 않았으면 recheckDays 뒤 다시 확인한다. maxRechecks번까지."""
    if alert.checks >= deps.config.notifications.max_rechecks:
        return
    checks = alert.checks + 1
    at = scheduler.next_digest(deps, as_of, days=deps.config.notifications.recheck_days)
    name = scheduler.schedule_name(user_id, NotificationType.POLICY_OPEN, alert.policy_id, f"c{checks}")
    deps.users.update_alert(user_id, alert.model_copy(update={"checks": checks, "scheduled_at": clock.iso(at),
                                                              "schedule_name": name}))
    deps.scheduler.create_once(name, at, scheduler.schedule_payload(user_id, NotificationType.POLICY_OPEN,
                                                                    alert.policy_id, checks))


def _policy_open(deps: Deps, payload: dict, as_of: datetime, simulated: bool) -> bool:
    user_id, policy_id = payload["userId"], payload["targetId"]
    alert = deps.users.get_alert(user_id, policy_id)
    if alert is None:
        return False
    policy = deps.catalog.get_policy(policy_id)
    if policy is None or (deps.config.policies.hide_unverified and not policy.verified):
        return False
    if not _is_open(policy, as_of):
        _recheck(deps, user_id, alert, as_of)
        return False
    result = _deliver(deps, payload, title=f"{policy.title} 신청을 받고 있어요", body=_policy_body(policy),
                      link=f"/opportunities/policies/{policy_id}", as_of=as_of, simulated=simulated)
    if result != Delivery.DEFERRED:
        deps.users.delete_alert(user_id, policy_id)  # 열리면 한 번 알리는 신청이라 알린 뒤 지운다
    return result == Delivery.SENT


HANDLERS = {NotificationType.TARGET_DEADLINE: _target_deadline, NotificationType.POLICY_OPEN: _policy_open}


def handle_schedule(deps: Deps, payload: dict, *, as_of: str | date | datetime | None = None,
                    simulated: bool = False) -> bool:
    """일정이 울리면 실제 상태를 다시 확인하고 알린다. 조건이 아니면 recheckDays 뒤 재확인 일정을 만든다.

    같은 알림은 한 번만 저장·발송한다 (T-10). 즉시 알림은 주 immediatePerWeek회까지이고 넘으면 다음 요약으로
    미룬다 (T-11). quietHours에는 보내지 않는다. 알렸으면 True.
    """
    user_id = payload.get("userId")
    try:
        kind = NotificationType(payload.get("type"))
    except ValueError:
        return False
    handler = HANDLERS.get(kind)
    if not user_id or not payload.get("targetId") or handler is None:
        return False
    moment = clock.resolve_as_of(as_of, deps.users.get_prefs(user_id).demo_as_of)
    return handler(deps, payload, moment, simulated)


# ---------------------------------------------------------------- 알림함
def check_new_opportunities(deps: Deps, user_id: str, *, cursor: str | None = None,
                            limit: int = 20) -> NotificationsResponse:
    """알림함 (최신순)."""
    items, next_cursor = deps.users.list_notifications(user_id, cursor=cursor, limit=limit)
    return NotificationsResponse(items=items, next_cursor=next_cursor)


def mark_read(deps: Deps, user_id: str, notification_id: str) -> bool:
    """읽음 표시. 없는 알림이면 False."""
    return deps.users.mark_notification_read(user_id, notification_id)


# ---------------------------------------------------------------- 데모 시간 앞당기기
def _due_jobs(deps: Deps, user_id: str, since: datetime, until: datetime) -> list[tuple[datetime, str, dict]]:
    """since < at <= until인 목표 공고 일정과 at <= until인 정책 알림."""
    jobs = []
    saved = [s for s in deps.users.list_saved(user_id) if s.kind == SavedKind.TARGET]
    postings = deps.catalog.batch_get_latest([s.job_posting_id for s in saved]) if saved else {}
    for item in saved:
        posting = postings.get(item.job_posting_id)
        if posting is None:
            continue
        for plan in scheduler.target_deadline_plan(deps, user_id, posting):
            if plan.name in item.schedule_names and since < plan.at <= until:
                jobs.append((plan.at, plan.name, scheduler.schedule_payload(
                    user_id, NotificationType.TARGET_DEADLINE, item.job_posting_id, plan.days)))
    for alert in deps.users.list_alerts(user_id):
        jobs.append(_alert_job(user_id, alert))
    return [job for job in jobs if job[0] <= until]


def _alert_job(user_id: str, alert: PolicyAlert) -> tuple[datetime, str, dict]:
    return (clock.parse_as_of(alert.scheduled_at), alert.schedule_name,
            scheduler.schedule_payload(user_id, NotificationType.POLICY_OPEN, alert.policy_id, alert.checks))


def advance_demo_clock(deps: Deps, user_id: str, as_of: str) -> DemoClockResponse:
    """데모 시간 앞당기기. demoAsOf를 저장하고 그 사이에 울릴 이 사용자의 일정을 바로 실행한다 (simulated=true)."""
    prefs = deps.users.get_prefs(user_id)
    since = clock.resolve_as_of(None, prefs.demo_as_of)
    until = clock.parse_as_of(as_of)
    deps.users.put_prefs(user_id, prefs.model_copy(update={"demo_as_of": clock.iso(until)}))

    pending = _due_jobs(deps, user_id, since, until)
    fired = 0
    runs = 0
    run_limit = len(pending) * (deps.config.notifications.max_rechecks + 2)  # 재확인이 끝없이 돌지 않게
    while pending and runs < run_limit:
        pending.sort(key=lambda job: (job[0], job[1]))
        at, name, payload = pending.pop(0)
        runs += 1
        if handle_schedule(deps, payload, as_of=at, simulated=True):
            fired += 1
        deps.scheduler.delete(name)  # 실제 일정은 실행 후 지워지므로 같게 맞춘다
        if payload["type"] == NotificationType.POLICY_OPEN:
            alert = deps.users.get_alert(user_id, payload["targetId"])
            if alert is not None and alert.checks > payload["check"]:  # 재확인 일정이 새로 생김
                next_job = _alert_job(user_id, alert)
                if next_job[0] <= until:
                    pending.append(next_job)
    return DemoClockResponse(as_of=clock.iso(until), fired=fired, simulated=True)
