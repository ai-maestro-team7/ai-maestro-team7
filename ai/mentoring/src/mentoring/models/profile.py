"""역량 프로필 (개발계획서1 §4.3, db-schema §2.1 `PROFILE#{profileId}#V#{n}`·`PROFILE#LATEST`).
버전은 고치지 않고 새로 쌓는다 (db-schema §0 원칙 5).
"""
from typing import Literal

from pydantic import Field

from .base import MentoringModel
from .enums import EvidenceLevel, FactStatus


class Evidence(MentoringModel):
    """원문 인용. start_char·end_char는 정규화 텍스트 기준이고 quoted_text와 그 구간이 같다 (A §4.3)."""
    evidence_id: str
    source_document_id: str
    page: int = Field(ge=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=1)
    quoted_text: str


class Skill(MentoringModel):
    skill_id: str
    name: str
    normalized_name: str | None = None
    ncs_unit_code: str | None = None  # 기준 데이터(team07-reference)에 있는 코드만
    evidence_level: EvidenceLevel
    fact_status: FactStatus
    evidence_ids: list[str] = Field(default_factory=list)


class ProfileEntry(MentoringModel):
    """프로젝트·경험. 원문 근거가 하나 이상 있는 것만 저장한다."""
    item_id: str
    name: str
    summary: str | None = None
    period: str | None = None
    fact_status: FactStatus
    evidence_ids: list[str] = Field(default_factory=list)


class Certificate(MentoringModel):
    item_id: str
    name: str
    fact_status: FactStatus
    evidence_ids: list[str] = Field(default_factory=list)


class CareerProfile(MentoringModel):
    schema_version: str = "2.0"
    profile_id: str
    profile_version: int = Field(ge=1)
    based_on_version: int | None = None
    owner_user_id: str
    created_by: Literal["EXTRACTION", "USER_CONFIRMATION"]
    source_document_ids: list[str] = Field(default_factory=list)
    target_role_preference: list[str] = Field(default_factory=list)
    skills: list[Skill] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    projects: list[ProfileEntry] = Field(default_factory=list)
    experiences: list[ProfileEntry] = Field(default_factory=list)
    certificates: list[Certificate] = Field(default_factory=list)
    needs_confirmation: list[str] = Field(default_factory=list)  # 확인이 필요한 역량·사실. 부족이 확정된 것이 아니다
    model_id: str | None = None
    prompt_version: str | None = None
    created_at: str

    def to_view(self) -> dict:
        """API 응답. 소유자 ID는 응답에 넣지 않는다."""
        data = self.to_api()
        data.pop("ownerUserId", None)
        return data


class ProfilePointer(MentoringModel):
    """`PROFILE#LATEST`."""
    owner_user_id: str
    latest_profile_id: str
    latest_version: int = Field(ge=1)
