"""정렬·이유·알림 설정 (B-07).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-07, §4.6.
"""

from ..deps import Deps
from ..models.api import PreferencesUpdate, PreferencesView
from ..models.enums import Sort, TrackEvent
from ..models.profile import OppPrefs
from . import clock


def _view(prefs: OppPrefs) -> PreferencesView:
    return PreferencesView(sort=prefs.sort, leave_reason=prefs.leave_reason, notifications=prefs.notifications,
                           receiving_policies=prefs.receiving_policies)


def get_preferences(deps: Deps, user_id: str) -> PreferencesView:
    """`OPP#PREFS`. 없으면 기본값."""
    return _view(deps.users.get_prefs(user_id))


def set_preferences(deps: Deps, user_id: str, update: PreferencesUpdate) -> PreferencesView:
    """보낸 필드만 바꾼다. 부산 우선 정렬을 끄면 BUSAN_FIRST_OFF 이벤트를 남긴다.

    leaveReason은 null을 보내면 지운다. sort·notifications·receivingPolicies의 null은 무시한다.
    이유를 직접 고르면 이유 질문을 다시 내려 주지 않는다 (B-07).
    """
    prefs = deps.users.get_prefs(user_id)
    sent = update.model_fields_set
    changes: dict = {}
    if "sort" in sent and update.sort is not None:
        changes["sort"] = update.sort
    if "leave_reason" in sent:
        changes["leave_reason"] = update.leave_reason
        if update.leave_reason is not None and not prefs.leave_reason_asked_at:
            changes["leave_reason_asked_at"] = clock.iso(clock.resolve_as_of(None, prefs.demo_as_of))
    if "notifications" in sent and update.notifications is not None:
        changes["notifications"] = update.notifications
    if "receiving_policies" in sent and update.receiving_policies is not None:
        changes["receiving_policies"] = list(dict.fromkeys(update.receiving_policies))  # 중복 제거, 순서 유지
    if not changes:
        return _view(prefs)
    updated = prefs.model_copy(update=changes)
    deps.users.put_prefs(user_id, updated)
    if prefs.sort == Sort.BUSAN_FIRST and updated.sort != Sort.BUSAN_FIRST:
        deps.events.emit(TrackEvent.BUSAN_FIRST_OFF, sort=str(updated.sort))
    return _view(updated)
