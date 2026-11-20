"""정형 NCS 기준 데이터 모델."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ReferenceModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class JobProfile(ReferenceModel):
    ncs_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None


class CompetencyUnit(ReferenceModel):
    ncs_code: str = Field(min_length=1)
    unit_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    training_hours: int | None = Field(default=None, ge=0)
    source_reference_date: str | None = None


class QualificationLink(ReferenceModel):
    unit_code: str = Field(min_length=1)
    qualification_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    unit_type: str = Field(min_length=1)
    training_hours: int | None = Field(default=None, ge=0)


class Qualification(ReferenceModel):
    """자격 정보 `QUAL#{qualCode}` / `META` (db-schema §4). 실재 확인과 공식 출처에 쓴다 (개발계획서1 F-05 처리 4단계)."""
    qualification_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    exam_agency: str | None = None
    source_url: str | None = None
    collected_at: str | None = None


class BasicSkill(ReferenceModel):
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    ability_id: int = Field(ge=1)
    sub_area_id: int = Field(ge=1)
    sub_area_name: str = Field(min_length=1)
