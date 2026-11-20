"""정렬·이유·알림 설정 (B-07).

담당 워크트리: api. 명세: 개발계획서2 §4.2 B-07, §4.6.
"""

from ..deps import Deps
from ..models.api import PreferencesUpdate, PreferencesView


def get_preferences(deps: Deps, user_id: str) -> PreferencesView:
    """`OPP#PREFS`. 없으면 기본값."""
    raise NotImplementedError("api 워크트리에서 구현한다")


def set_preferences(deps: Deps, user_id: str, update: PreferencesUpdate) -> PreferencesView:
    """보낸 필드만 바꾼다. 부산 우선 정렬을 끄면 BUSAN_FIRST_OFF 이벤트를 남긴다."""
    raise NotImplementedError("api 워크트리에서 구현한다")
