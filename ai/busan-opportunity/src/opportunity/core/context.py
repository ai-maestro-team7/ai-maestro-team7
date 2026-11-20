"""요청마다 처음에 하는 일: 프로필·설정 읽기, 기준 시각 정하기, 데이터 기준일 확인."""

from dataclasses import dataclass
from datetime import date, datetime

from ..deps import Deps
from ..models.errors import profile_incomplete
from ..models.profile import BasicProfile, OppPrefs
from . import clock


@dataclass
class UserContext:
    user_id: str
    profile: BasicProfile
    prefs: OppPrefs
    as_of: datetime


def load_context(deps: Deps, user_id: str, as_of: str | date | datetime | None = None, *,
                 require_jobs: bool = False) -> UserContext:
    """userId는 입구가 인증 정보에서 읽어 넘긴다. 요청 본문이나 모델 파라미터의 값은 쓰지 않는다.

    require_jobs=True인데 희망 직무가 없으면 PROFILE_INCOMPLETE (422).
    """
    profile = deps.users.get_basic_profile(user_id) or BasicProfile()
    prefs = deps.users.get_prefs(user_id)
    if require_jobs and not profile.desired_jobs:
        raise profile_incomplete(["desiredJobs"])
    return UserContext(user_id, profile, prefs, clock.resolve_as_of(as_of, prefs.demo_as_of))


def freshness(deps: Deps, as_of: datetime) -> tuple[str | None, bool]:
    """(dataAsOf, stale). 수집이 staleAfterHours 넘게 멈췄으면 stale=true."""
    data_as_of = deps.catalog.data_as_of()
    if data_as_of is None:
        return None, True
    stale = clock.hours_between(data_as_of, as_of) > deps.config.data.stale_after_hours
    return data_as_of, stale
