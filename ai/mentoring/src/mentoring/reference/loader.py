"""db-schema §4와 기존 team07-reference 형식의 멱등 적재 계획과 실행."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict

from .csv_data import CsvData


class LoadReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dry_run: bool
    counts: dict[str, int]
    total: int
    written: int


def _optional(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if value not in (None, "", [])}


def _int(value: str) -> int | None:
    return int(value) if value else None


class ReferenceLoader:
    def __init__(self, root: str) -> None:
        self._data = CsvData(root)

    def items(self) -> list[dict[str, Any]]:
        rows = self._data.rows
        classifications = {row["ncs_subcategory_code"]: row for row in rows["classifications"]}
        items: list[dict[str, Any]] = []

        for row in rows["profiles"]:
            code = row["ncs_subcategory_code"]
            classification = classifications.get(code, {})
            items.append(
                _optional(
                    {
                        "PK": f"NCS#{code}",
                        "SK": "PROFILE",
                        "GSI1PK": f"JOBNAME#{row['job_role']}",
                        "GSI1SK": f"NCS#{code}",
                        "entityType": "NcsJobProfile",
                        "schemaVersion": "1.0",
                        "sourceFile": "selected_job_profiles.csv",
                        "documentId": row.get("document_id"),
                        "jobFamily": row.get("job_family"),
                        "jobRole": row.get("job_role"),
                        "ncsCode": code,
                        "ncsLargeCategoryCode": classification.get("ncs_large_category_code"),
                        "occupationName": row.get("occupation_name"),
                        "occupationDefinition": row.get("occupation_definition"),
                        "sourceUrl": row.get("source_url"),
                        "collectedAt": row.get("collected_at"),
                        "originalPublishedAt": row.get("original_published_at"),
                        "sourceReferenceDate": row.get("source_reference_date"),
                        "verificationStatus": row.get("verification_status"),
                        "license": row.get("license"),
                    }
                )
            )

        for row in rows["units"]:
            code = row["ncs_subcategory_code"]
            unit_code = row["competency_unit_code"]
            items.append(
                _optional(
                    {
                        "PK": f"NCS#{code}",
                        "SK": f"UNIT#{unit_code}",
                        "entityType": "CompetencyUnit",
                        "schemaVersion": "1.0",
                        "sourceFile": "selected_competency_units.csv",
                        "documentId": row.get("document_id"),
                        "jobRole": row.get("job_role"),
                        "ncsCode": code,
                        "competencyUnitCode": unit_code,
                        "competencyUnitName": row.get("competency_unit_name"),
                        "trainingObjective": row.get("training_objective"),
                        "trainingHours": _int(row.get("training_hours", "")),
                        "sourceUrl": row.get("source_url"),
                        "collectedAt": row.get("collected_at"),
                        "originalPublishedAt": row.get("original_published_at"),
                        "sourceReferenceDate": row.get("source_reference_date"),
                        "verificationStatus": row.get("verification_status"),
                        "license": row.get("license"),
                    }
                )
            )

        groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in rows["qualifications"]:
            groups[(row["competency_unit_code"], row["qualification_code"], row["unit_type"])].append(row)

        qualifications: dict[str, dict[str, Any]] = {}
        for (unit_code, qualification_code, unit_type), group in sorted(groups.items()):
            row = group[0]
            hour_values = sorted(
                {int(item["minimum_training_hours"]) for item in group if item.get("minimum_training_hours")}
            )
            hour_fields: dict[str, Any] = {}
            if len(hour_values) == 1:
                hour_fields["minimumTrainingHours"] = hour_values[0]
            elif len(hour_values) > 1:
                hour_fields["minimumTrainingHoursValues"] = hour_values
                hour_fields["trainingHoursConflict"] = True
            items.append(
                _optional(
                    {
                        "PK": f"UNIT#{unit_code}",
                        "SK": f"QUAL#{qualification_code}#{unit_type}",
                        "GSI1PK": f"QUAL#{qualification_code}",
                        "GSI1SK": f"UNIT#{unit_code}",
                        "entityType": "QualificationLink",
                        "schemaVersion": "1.0",
                        "sourceFile": "selected_qualification_links.csv",
                        "ncsCode": row.get("ncs_subcategory_code"),
                        "jobRole": row.get("job_role"),
                        "competencyUnitCode": unit_code,
                        "competencyUnitName": row.get("competency_unit_name"),
                        "qualificationCode": qualification_code,
                        "qualificationName": row.get("qualification_name"),
                        "unitType": unit_type,
                        "examAgency": row.get("exam_agency"),
                        **hour_fields,
                        "sourceRows": len(group),
                        "sourceUrl": row.get("source_url"),
                        "collectedAt": row.get("collected_at"),
                        "originalPublishedAt": row.get("original_published_at"),
                        "verificationStatus": row.get("verification_status"),
                        "license": row.get("license"),
                    }
                )
            )
            qualifications.setdefault(
                qualification_code,
                _optional(
                    {
                        "PK": f"QUAL#{qualification_code}",
                        "SK": "META",
                        "entityType": "Qualification",
                        "schemaVersion": "1.0",
                        "sourceFile": "selected_qualification_links.csv",
                        "qualificationCode": qualification_code,
                        "qualificationName": row.get("qualification_name"),
                        "examAgency": row.get("exam_agency"),
                        "sourceUrl": row.get("source_url"),
                        "collectedAt": row.get("collected_at"),
                        "originalPublishedAt": row.get("original_published_at"),
                        "verificationStatus": row.get("verification_status"),
                        "license": row.get("license"),
                    }
                ),
            )
        items.extend(qualifications.values())

        for row in rows["basic_skills"]:
            number = int(row["순번"])
            items.append(
                {
                    "PK": "BASIC",
                    "SK": f"SKILL#{number:03d}",
                    "entityType": "NcsBasicSkill",
                    "schemaVersion": "1.0",
                    "sourceFile": "ncs_basic_skills.csv",
                    "skillNo": number,
                    "abilityId": int(row["직업기초능력일련번호"]),
                    "abilityName": row["직업기초능력명"],
                    "subAreaId": int(row["하위영역일련번호"]),
                    "subAreaName": row["하위영역명"],
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

        now = datetime.now(timezone(timedelta(hours=9))).replace(microsecond=0).isoformat()
        with table.batch_writer(overwrite_by_pkeys=["PK", "SK"]) as batch:
            for item in planned:
                existing = table.get_item(Key={"PK": item["PK"], "SK": item["SK"]}).get("Item", {})
                item["loadedAt"] = existing.get("loadedAt", now)
                batch.put_item(Item=item)
        return LoadReport(dry_run=False, counts=counts, total=len(planned), written=len(planned))
