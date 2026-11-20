"""CSV와 DynamoDB가 같은 결과를 내는 NCS 정확 조회 구현."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Protocol

from .csv_data import CsvData
from .models import BasicSkill, CompetencyUnit, JobProfile, QualificationLink


class ReferenceLookup(Protocol):
    def get_job_profile(self, ncs_code: str) -> JobProfile | None: ...

    def find_job_profiles_by_name(self, name: str) -> list[JobProfile]: ...

    def list_units(self, ncs_code: str) -> list[CompetencyUnit]: ...

    def get_unit(self, ncs_code: str, unit_code: str) -> CompetencyUnit | None: ...

    def list_qualification_links(self, unit_code: str) -> list[QualificationLink]: ...

    def list_basic_skills(self) -> list[BasicSkill]: ...


class CsvReferenceLookup:
    def __init__(self, root: str) -> None:
        self._data = CsvData(root)

    def get_job_profile(self, ncs_code: str) -> JobProfile | None:
        return next((item for item in self._data.job_profiles if item.ncs_code == ncs_code), None)

    def find_job_profiles_by_name(self, name: str) -> list[JobProfile]:
        return sorted((item for item in self._data.job_profiles if item.name == name), key=lambda item: item.ncs_code)

    def list_units(self, ncs_code: str) -> list[CompetencyUnit]:
        return sorted((item for item in self._data.units if item.ncs_code == ncs_code), key=lambda item: item.unit_code)

    def get_unit(self, ncs_code: str, unit_code: str) -> CompetencyUnit | None:
        return next(
            (item for item in self._data.units if item.ncs_code == ncs_code and item.unit_code == unit_code),
            None,
        )

    def list_qualification_links(self, unit_code: str) -> list[QualificationLink]:
        return [item for item in self._data.qualification_links if item.unit_code == unit_code]

    def list_basic_skills(self) -> list[BasicSkill]:
        return sorted(self._data.basic_skills, key=lambda item: item.skill_id)


class DynamoReferenceLookup:
    def __init__(self, table: Any) -> None:
        self._table = table

    @classmethod
    def from_environment(
        cls, dynamodb_resource: Any, environ: Mapping[str, str] | None = None
    ) -> "DynamoReferenceLookup":
        values = os.environ if environ is None else environ
        table_name = values.get("TABLE_REFERENCE")
        if not table_name:
            raise RuntimeError("TABLE_REFERENCE 환경변수가 필요합니다.")
        return cls(dynamodb_resource.Table(table_name))

    @staticmethod
    def _profile(item: Mapping[str, Any]) -> JobProfile:
        return JobProfile(
            ncs_code=str(item["ncsCode"]),
            name=str(item["jobRole"]),
            description=str(item["occupationDefinition"]) if item.get("occupationDefinition") else None,
        )

    @staticmethod
    def _unit(item: Mapping[str, Any]) -> CompetencyUnit:
        return CompetencyUnit(
            ncs_code=str(item["ncsCode"]),
            unit_code=str(item["competencyUnitCode"]),
            name=str(item["competencyUnitName"]),
            training_hours=int(item["trainingHours"]) if item.get("trainingHours") is not None else None,
            source_reference_date=str(item["sourceReferenceDate"]) if item.get("sourceReferenceDate") else None,
        )

    @staticmethod
    def _link(item: Mapping[str, Any]) -> QualificationLink:
        return QualificationLink(
            unit_code=str(item["competencyUnitCode"]),
            qualification_code=str(item["qualificationCode"]),
            name=str(item["qualificationName"]),
            unit_type=str(item["unitType"]),
            training_hours=(
                int(item["minimumTrainingHours"])
                if item.get("minimumTrainingHours") is not None
                else (
                    int(item["minimumTrainingHoursValues"][0])
                    if item.get("minimumTrainingHoursValues")
                    else None
                )
            ),
        )

    def get_job_profile(self, ncs_code: str) -> JobProfile | None:
        item = self._table.get_item(Key={"PK": f"NCS#{ncs_code}", "SK": "PROFILE"}).get("Item")
        return self._profile(item) if item else None

    def find_job_profiles_by_name(self, name: str) -> list[JobProfile]:
        from boto3.dynamodb.conditions import Key

        items = self._table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("GSI1PK").eq(f"JOBNAME#{name}"),
        ).get("Items", [])
        return sorted((self._profile(item) for item in items), key=lambda item: item.ncs_code)

    def list_units(self, ncs_code: str) -> list[CompetencyUnit]:
        from boto3.dynamodb.conditions import Key

        items = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"NCS#{ncs_code}") & Key("SK").begins_with("UNIT#")
        ).get("Items", [])
        return sorted((self._unit(item) for item in items), key=lambda item: item.unit_code)

    def get_unit(self, ncs_code: str, unit_code: str) -> CompetencyUnit | None:
        item = self._table.get_item(
            Key={"PK": f"NCS#{ncs_code}", "SK": f"UNIT#{unit_code}"}
        ).get("Item")
        return self._unit(item) if item else None

    def list_qualification_links(self, unit_code: str) -> list[QualificationLink]:
        from boto3.dynamodb.conditions import Key

        items = self._table.query(
            KeyConditionExpression=Key("PK").eq(f"UNIT#{unit_code}") & Key("SK").begins_with("QUAL#")
        ).get("Items", [])
        return sorted(
            (self._link(item) for item in items),
            key=lambda item: (item.qualification_code, item.unit_type),
        )

    def list_basic_skills(self) -> list[BasicSkill]:
        from boto3.dynamodb.conditions import Key

        items = self._table.query(
            KeyConditionExpression=Key("PK").eq("BASIC") & Key("SK").begins_with("SKILL#")
        ).get("Items", [])
        return sorted(
            (
                BasicSkill(
                    skill_id=f"{int(item['skillNo']):03d}",
                    name=str(item["abilityName"]),
                    ability_id=int(item["abilityId"]),
                    sub_area_id=int(item["subAreaId"]),
                    sub_area_name=str(item["subAreaName"]),
                )
                for item in items
            ),
            key=lambda item: item.skill_id,
        )
