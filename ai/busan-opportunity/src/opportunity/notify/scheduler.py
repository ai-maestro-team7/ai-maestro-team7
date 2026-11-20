"""일회성 일정 예약 (EventBridge Scheduler).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-09·B-10.

일정 payload는 `{"userId", "type", "targetId", "check"}`다.
- TARGET_DEADLINE: check는 마감 며칠 전 일정인지 (7, 3)
- POLICY_OPEN: check는 지금까지 재확인한 횟수 (0부터)
알림을 다음 요약으로 미룰 때만 `"digest": true`가 더 붙는다 (notifier).
"""

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..core import clock
from ..core.copy_rules import deadline_label
from ..deps import Deps
from ..models.api import PolicyAlertResponse, PolicyAlertView, ScheduleView
from ..models.enums import NotificationType
from ..models.errors import policy_not_found
from ..models.policy import Policy
from ..models.posting import PostingLatest
from ..models.user_state import PolicyAlert

NAME_PREFIX = "team07-opp-"
NAME_MAX = 64  # EventBridge Scheduler 이름 길이 한도
_SLUG = re.compile(r"[^a-z0-9]+")


def schedule_name(user_id: str, kind: str, target_id: str, suffix: str = "") -> str:
    """일정 이름. 사용자·대상 해시로 고정해 64자 안에 둔다. 사용자 ID 원문은 넣지 않는다."""
    digest = hashlib.sha256(f"{user_id}|{kind}|{target_id}|{suffix}".encode()).hexdigest()
    slug = _SLUG.sub("-", str(kind).lower()).strip("-")[:16]
    return f"{NAME_PREFIX}{slug}-{digest}"[:NAME_MAX]


def schedule_payload(user_id: str, kind: NotificationType, target_id: str, check: int) -> dict:
    return {"userId": user_id, "type": str(kind), "targetId": target_id, "check": check}


# ---------------------------------------------------------------- 목표 공고 마감 (B-09)
@dataclass
class PlannedSchedule:
    days: int
    name: str
    at: datetime


def target_deadline_plan(deps: Deps, user_id: str, posting: PostingLatest) -> list[PlannedSchedule]:
    """마감 deadlineDays일 전 digestHour시 일정 목록. 상시 채용은 빈 목록. 지난 날짜도 걸러 내지 않는다."""
    if posting.rolling or clock.is_rolling(posting.closes_at):
        return []
    closes = date.fromisoformat(posting.closes_at)
    hour = deps.config.notifications.digest_hour
    return [PlannedSchedule(days, schedule_name(user_id, NotificationType.TARGET_DEADLINE, posting.job_posting_id,
                                                f"d{days}"),
                            clock.at_hour(closes - timedelta(days=days), hour))
            for days in deps.config.notifications.deadline_days]


def upcoming_target_deadlines(deps: Deps, user_id: str, posting: PostingLatest, *,
                              as_of: datetime) -> list[PlannedSchedule]:
    """as_of 뒤에 울릴 일정만. 마감된 공고는 빈 목록."""
    if posting.is_expired or clock.is_expired(posting.closes_at, as_of):
        return []
    return [p for p in target_deadline_plan(deps, user_id, posting) if p.at > as_of]


def schedule_target_deadlines(deps: Deps, user_id: str, posting: PostingLatest, *,
                              as_of: datetime) -> list[ScheduleView]:
    """목표 공고의 마감 D-7·D-3 일정을 만든다 (digestHour시). 이미 지난 날짜와 상시 채용은 만들지 않는다."""
    views = []
    for plan in upcoming_target_deadlines(deps, user_id, posting, as_of=as_of):
        # 같은 이름이 이미 있으면 False가 오지만 오류로 다루지 않는다 (B-09)
        deps.scheduler.create_once(plan.name, plan.at, schedule_payload(
            user_id, NotificationType.TARGET_DEADLINE, posting.job_posting_id, plan.days))
        views.append(ScheduleView(type=NotificationType.TARGET_DEADLINE, at=clock.iso(plan.at),
                                  label=deadline_label(plan.days)))
    return views


# ---------------------------------------------------------------- 정책 열리면 알림 (B-10)
def next_digest(deps: Deps, after: datetime, *, days: int = 0) -> datetime:
    """after + days일 뒤의 digestHour시. days=0이면 after 뒤 가장 가까운 digestHour시."""
    hour = deps.config.notifications.digest_hour
    at = clock.at_hour(clock.day(after + timedelta(days=days)), hour)
    return at if at > after else at + timedelta(days=1)


def _add_year(value: date) -> date:
    try:
        return value.replace(year=value.year + 1)
    except ValueError:  # 2월 29일
        return value.replace(year=value.year + 1, day=28)


def policy_open_at(deps: Deps, policy: Policy, as_of: datetime) -> datetime:
    """작년 모집 시작일에 1년을 더한 날의 digestHour시. 모르거나 이미 지났으면 recheckDays 뒤."""
    if policy.last_cycle:
        start = _add_year(date.fromisoformat(policy.last_cycle.start))
        at = clock.at_hour(start, deps.config.notifications.digest_hour)
        if at > as_of:
            return at
    return next_digest(deps, as_of, days=deps.config.notifications.recheck_days)


def visible_policy(deps: Deps, policy_id: str) -> Policy:
    """없거나 검수 전(verified=false)이면 POLICY_NOT_FOUND (T-07)."""
    policy = deps.catalog.get_policy(policy_id)
    if policy is None or (deps.config.policies.hide_unverified and not policy.verified):
        raise policy_not_found(policy_id)
    return policy


def _alert_response(alert: PolicyAlert, created: bool) -> PolicyAlertResponse:
    return PolicyAlertResponse(alert=PolicyAlertView(policy_id=alert.policy_id, scheduled_at=alert.scheduled_at),
                               created=created)


def subscribe_policy_alert(deps: Deps, user_id: str, policy_id: str, *, idempotency_key: str | None = None,
                           as_of: str | date | datetime | None = None) -> PolicyAlertResponse:
    """정책이 열리면 알림. 이미 신청했으면 같은 결과를 다시 돌려준다."""
    from ..core.context import load_context
    from ..core.saved import idempotent  # saved가 이 모듈을 import하므로 여기서 부른다

    visible_policy(deps, policy_id)  # 없는 정책은 멱등 기록을 남기기 전에 걸러 낸다

    def run() -> PolicyAlertResponse:
        policy = visible_policy(deps, policy_id)
        existing = deps.users.get_alert(user_id, policy_id)
        if existing is not None:
            return _alert_response(existing, False)
        ctx = load_context(deps, user_id, as_of)
        at = policy_open_at(deps, policy, ctx.as_of)
        name = schedule_name(user_id, NotificationType.POLICY_OPEN, policy_id, "c0")
        alert = PolicyAlert(policy_id=policy_id, scheduled_at=clock.iso(at), schedule_name=name, checks=0)
        if not deps.users.put_alert(user_id, alert):
            return _alert_response(deps.users.get_alert(user_id, policy_id) or alert, False)
        deps.scheduler.create_once(name, at, schedule_payload(user_id, NotificationType.POLICY_OPEN, policy_id, 0))
        return _alert_response(alert, True)

    return idempotent(deps, user_id, idempotency_key, "policy-alert", {"policyId": policy_id},
                      PolicyAlertResponse, run)
