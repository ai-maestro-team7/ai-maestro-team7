"""db-schema §4 형식의 멱등 Reference 적재 계획과 실행."""

from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from .csv_data import CsvData


class LoadReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dry_run: bool
    counts: dict[str, int]
    total: int
    written: int


class ReferenceLoader:
    def __init__(self, root: str) -> None:
        self._data = CsvData(root)

    def items(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for profile in self._data.job_profiles:
            item = {
                "PK": f"NCS#{profile.ncs_code}",
                "SK": "PROFILE",
                "GSI1PK": f"JOBNAME#{profile.name}",
                "GSI1SK": f"NCS#{profile.ncs_code}",
                "entityType": "NCS_PROFILE",
                **profile.model_dump(by_alias=True),
            }
            items.append(item)
        for unit in self._data.units:
            items.append(
                {
                    "PK": f"NCS#{unit.ncs_code}",
                    "SK": f"UNIT#{unit.unit_code}",
                    "entityType": "COMPETENCY_UNIT",
                    **unit.model_dump(by_alias=True),
                }
            )
        qualification_meta: dict[str, dict[str, Any]] = {}
        for link in self._data.qualification_links:
            items.append(
                {
                    "PK": f"UNIT#{link.unit_code}",
                    "SK": f"QUAL#{link.qualification_code}#{link.unit_type}",
                    "GSI1PK": f"QUAL#{link.qualification_code}",
                    "GSI1SK": f"UNIT#{link.unit_code}",
                    "entityType": "QUALIFICATION_LINK",
                    **link.model_dump(by_alias=True),
                }
            )
            qualification_meta.setdefault(
                link.qualification_code,
                {
                    "PK": f"QUAL#{link.qualification_code}",
                    "SK": "META",
                    "entityType": "QUALIFICATION",
                    "qualificationCode": link.qualification_code,
                    "name": link.name,
                },
            )
        items.extend(qualification_meta.values())
        for skill in self._data.basic_skills:
            items.append(
                {
                    "PK": "BASIC",
                    "SK": f"SKILL#{skill.skill_id}",
                    "entityType": "BASIC_SKILL",
                    **skill.model_dump(by_alias=True),
                }
            )
        return sorted(items, key=lambda item: (item["PK"], item["SK"]))

    def load(self, table: Any | None = None, *, write: bool = False) -> LoadReport:
        planned = self.items()
        counts = dict(Counter(str(item["entityType"]) for item in planned))
        if not write:
            return LoadReport(dry_run=True, counts=counts, total=len(planned), written=0)
        if table is None:
            raise ValueError("write=True일 때 DynamoDB table이 필요합니다.")
        with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
            for item in planned:
                batch.put_item(Item=item)
        return LoadReport(dry_run=False, counts=counts, total=len(planned), written=len(planned))
