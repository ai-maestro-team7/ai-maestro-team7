"""정책 지갑 (B-08). 판정은 규칙으로 하고, 서울과 부산을 같은 함수로 계산한다.

담당 워크트리: core-policy. 명세: 개발계획서2 §4.2 B-08. 테스트: T-06, T-07, T-12, T-13, T-14.
"""

from datetime import date, datetime

from ..deps import Deps
from ..models.api import PolicyBrief, PolicyDetailResponse, PolicyJudgement, PolicyWalletResponse, RegionalPolicyCount
from ..models.enums import PolicyStage
from ..models.policy import Policy
from ..models.posting import PostingLatest
from ..models.profile import BasicProfile, OppPrefs


def judge_policy(policy: Policy, profile: BasicProfile, prefs: OppPrefs, *, as_of: datetime,
                 assumed_sido: str | None = None) -> PolicyJudgement:
    """정책 하나를 판정한다. assumed_sido를 주면 그 시·도에 산다고 가정한다 (비교 패널).

    나이가 범위 경계에 걸치면 CHECK_NEEDED (T-12), 소득 조건이 있는데 미입력이면 CHECK_NEEDED (T-13),
    받는 중인 정책과 중복 불가면 NOT_ELIGIBLE (T-14). 자유 서술 조건은 판정에 쓰지 않고 manualChecks로 돌려준다.
    """
    raise NotImplementedError("core-policy 워크트리에서 구현한다")


def match_policies(deps: Deps, user_id: str, *, stage: PolicyStage | None = None,
                   as_of: str | date | datetime | None = None) -> PolicyWalletResponse:
    """정책 지갑. OPEN_NOW, NEXT_CYCLE, AFTER_EMPLOYMENT, SETTLEMENT, CLOSED로 나눈다.

    verified=false 정책은 내보내지 않는다 (T-07). 합계는 자격만 맞으면 받는 금액과 선정돼야 받는 최대 금액으로
    나누고 본인 저축분은 더하지 않는다.
    """
    raise NotImplementedError("core-policy 워크트리에서 구현한다")


def get_policy(deps: Deps, user_id: str, policy_id: str, *,
               as_of: str | date | datetime | None = None) -> PolicyDetailResponse:
    """정책 상세, 판정 이유, 체크리스트. 없거나 verified=false면 POLICY_NOT_FOUND."""
    raise NotImplementedError("core-policy 워크트리에서 구현한다")


def count_regional_policies(deps: Deps, profile: BasicProfile, prefs: OppPrefs, sido: str, *,
                            as_of: datetime) -> RegionalPolicyCount:
    """그 시·도에 산다고 가정했을 때 맞는 지역 정책 수와 금액. 온통청년 출처만 센다 (T-06).

    서울과 부산을 이 함수 하나로 계산한다. 직접 정리한 부산 시드는 세지 않는다.
    """
    raise NotImplementedError("core-policy 워크트리에서 구현한다")


def related_policies(deps: Deps, profile: BasicProfile, prefs: OppPrefs, posting: PostingLatest, *,
                     as_of: datetime, limit: int = 3) -> list[PolicyBrief]:
    """이 공고에 취업하면 받을 수 있는 정책 (공고 근무지 기준). 부산 공고가 아니면 빈 목록."""
    raise NotImplementedError("core-policy 워크트리에서 구현한다")
