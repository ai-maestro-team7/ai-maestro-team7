"""면접용 역량 요약 `CareerProfileSummary` (Requirement 8, D-12, 계약 `team07_contracts.career_summary`).

백엔드(`backend/interview_api.py`의 `load_latest_profile()`, BE-5)가 저장된 역량 프로필 항목을 넣고 부른다.
- skills: 사용자가 확인한(VERIFIED) 보유 역량 이름만. 미보유로 확인한 것은 넣지 않는다
- projects: 원문 근거가 있는 프로젝트·경험의 이름(과 요약)
- needsConfirmation: 확인이 필요한 역량. 부족이 확정된 역량이 아니다
- 원문, 인용문, 연락처는 넣지 않는다 (A §12.2 allowRawResume: false)
- 한도를 넘는 목록은 저장 순서대로 앞에서부터 자른다. 고르는 규칙은 미결정 M-5다
면접 평가를 프로필로 되돌리는 함수는 두지 않는다 (Requirement 8 기준 5).
"""
from collections.abc import Mapping

from team07_contracts import CAREER_SUMMARY_LIMITS, dump, validate
from team07_contracts.validation import ContractValidationError

from ..models import CareerProfile, EvidenceLevel, FactStatus

SCHEMA_VERSION = "1.0"


def to_career_profile_summary(profile: CareerProfile | Mapping) -> dict | None:
    """계약 검사를 통과한 요약 dict(카멜 키)를 돌려준다. 만들 수 없으면 None (백엔드는 profile=None으로 넘긴다)."""
    try:
        if not isinstance(profile, CareerProfile):
            profile = CareerProfile.model_validate(dict(profile))
    except ValueError:
        return None

    skills = [s.name for s in profile.skills
              if s.fact_status == FactStatus.VERIFIED and s.evidence_level != EvidenceLevel.USER_CONFIRMED_GAP]
    projects = [_label(e.name, e.summary, CAREER_SUMMARY_LIMITS["projects"][1])
                for e in [*profile.projects, *profile.experiences]]
    needs = [s.name for s in profile.skills if s.fact_status == FactStatus.NEEDS_CONFIRMATION]
    needs += profile.needs_confirmation

    data = {
        "projects": _fit(projects, "projects"),
        "skills": _fit(skills, "skills"),
        "needsConfirmation": _fit(needs, "needsConfirmation"),
        "profileId": profile.profile_id,
        "profileVersion": profile.profile_version,
    }
    try:
        return dump(validate("CareerProfileSummary", data, schema_version=SCHEMA_VERSION))
    except (ContractValidationError, ValueError):
        return None


def _label(name: str, summary: str | None, max_chars: int) -> str | None:
    if summary:
        combined = f"{name}: {summary}"
        if len(combined) <= max_chars:
            return combined
    return name


def _fit(values: list[str | None], key: str) -> list[str]:
    max_items, max_chars = CAREER_SUMMARY_LIMITS[key]
    out: list[str] = []
    for value in values:
        text = (value or "").strip()
        if text and len(text) <= max_chars and text not in out:
            out.append(text)
        if len(out) == max_items:
            break
    return out
