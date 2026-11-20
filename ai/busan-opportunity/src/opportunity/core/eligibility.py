"""공고 지원 자격. 판정 규칙은 여기 두지 않는다.

판정은 공통 함수 `backend/eligibility.py`의 `evaluate_eligibility` 하나로만 한다 (D-11).
입구가 그 함수를 `Deps.eligibility`로 넣어 주고, 여기서는 부르고 모양만 맞춘다.
"""

from ..deps import Deps
from ..models.api import EligibilityResult
from ..models.enums import ConditionResult
from ..models.posting import EligibilityRule
from ..models.profile import BasicProfile


def judge(deps: Deps, profile: BasicProfile, rules: list[EligibilityRule]) -> EligibilityResult:
    raw = deps.eligibility(profile.to_api(), [rule.to_api() for rule in rules])
    return EligibilityResult.model_validate(raw)


def required_ratio(result: EligibilityResult, unknown_value: float) -> float | None:
    """확인할 수 있는 필수 조건 중 충족 비율. UNKNOWN은 unknown_value로 센다. 조건이 없으면 None (측정 불가)."""
    if not result.conditions:
        return None
    score = {ConditionResult.MET: 1.0, ConditionResult.NOT_MET: 0.0, ConditionResult.UNKNOWN: unknown_value}
    return sum(score[c.result] for c in result.conditions) / len(result.conditions)
