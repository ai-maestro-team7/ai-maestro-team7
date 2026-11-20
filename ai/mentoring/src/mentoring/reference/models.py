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
    data: dict[str, str] = Field(default_factory=dict)


class CompetencyUnit(ReferenceModel):
    ncs_code: str = Field(min_length=1)
    unit_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    training_hours: int | None = Field(default=None, ge=0)
    source_reference_date: str | None = None
    data: dict[str, str] = Field(default_factory=dict)


class QualificationLink(ReferenceModel):
    unit_code: str = Field(min_length=1)
    qualification_code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    unit_type: str = Field(min_length=1)
    training_hours: int | None = Field(default=None, ge=0)
    data: dict[str, str] = Field(default_factory=dict)


class BasicSkill(ReferenceModel):
    skill_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    data: dict[str, str] = Field(default_factory=dict)
