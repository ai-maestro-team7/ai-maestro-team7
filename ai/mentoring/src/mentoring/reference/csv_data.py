"""지식 패키지 structured CSV를 UTF-8로 읽는 내부 도구."""

from __future__ import annotations

import csv
from pathlib import Path

from .models import BasicSkill, CompetencyUnit, JobProfile, QualificationLink

FILES = {
    "profiles": "selected_job_profiles.csv",
    "units": "selected_competency_units.csv",
    "qualifications": "selected_qualification_links.csv",
    "classifications": "selected_ncs_classification.csv",
    "basic_skills": "ncs_basic_skills.csv",
}


def _read(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            return [{key.strip(): (value or "").strip() for key, value in row.items()} for row in csv.DictReader(stream)]
    except UnicodeDecodeError as exc:
        raise ValueError(f"UTF-8 CSV만 사용할 수 있습니다: {path.name}") from exc


def _value(row: dict[str, str], *names: str, required: bool = True) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    if required:
        raise ValueError(f"CSV 필수 열 값이 없습니다: {' / '.join(names)}")
    return ""


def _integer(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(float(value.replace(",", "")))
    except ValueError as exc:
        raise ValueError("training_hours는 0 이상의 정수여야 합니다") from exc


class CsvData:
    """5개 structured CSV를 한 번 읽어 정규화한 스냅샷."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        rows = {name: _read(self.root / filename) for name, filename in FILES.items()}
        self.rows = rows
        classifications: dict[str, dict[str, str]] = {}
        for row in rows["classifications"]:
            code = _value(row, "ncs_subcategory_code", "ncs_code")
            classifications[code] = row

        self.job_profiles: list[JobProfile] = []
        for row in rows["profiles"]:
            code = _value(row, "ncs_subcategory_code", "ncs_code")
            self.job_profiles.append(
                JobProfile(
                    ncs_code=code,
                    name=_value(row, "job_role", "job_name", "ncs_subcategory_name", "name"),
                    description=_value(
                        row, "job_description", "occupation_definition", "description", required=False
                    )
                    or None,
                )
            )

        self.units: list[CompetencyUnit] = []
        for row in rows["units"]:
            self.units.append(
                CompetencyUnit(
                    ncs_code=_value(row, "ncs_subcategory_code", "ncs_code"),
                    unit_code=_value(row, "competency_unit_code", "unit_code"),
                    name=_value(row, "competency_unit_name", "unit_name", "name"),
                    training_hours=_integer(
                        _value(row, "training_hours", "minimum_training_hours", required=False)
                    ),
                    source_reference_date=_value(row, "source_reference_date", required=False) or None,
                )
            )

        links: dict[tuple[str, str, str], QualificationLink] = {}
        for row in rows["qualifications"]:
            unit_code = _value(row, "competency_unit_code", "unit_code")
            qualification_code = _value(row, "qualification_code", "qual_code")
            unit_type = _value(row, "unit_type", "qualification_unit_type", "link_type")
            key = (unit_code, qualification_code, unit_type)
            if key not in links:
                links[key] = QualificationLink(
                    unit_code=unit_code,
                    qualification_code=qualification_code,
                    name=_value(row, "qualification_name", "qual_name", "name"),
                    unit_type=unit_type,
                    training_hours=_integer(
                        _value(row, "training_hours", "minimum_training_hours", required=False)
                    ),
                )
        self.qualification_links = sorted(
            links.values(), key=lambda item: (item.unit_code, item.qualification_code, item.unit_type)
        )

        self.basic_skills: list[BasicSkill] = []
        for index, row in enumerate(rows["basic_skills"], start=1):
            self.basic_skills.append(
                BasicSkill(
                    skill_id=f"{int(_value(row, '순번', required=False) or index):03d}",
                    name=_value(row, "skill_name", "basic_skill_name", "직업기초능력명", "name"),
                    ability_id=int(_value(row, "직업기초능력일련번호", required=False) or index),
                    sub_area_id=int(_value(row, "하위영역일련번호", required=False) or 1),
                    sub_area_name=_value(
                        row, "하위영역명", "sub_area_name", required=False
                    )
                    or _value(row, "skill_name", "basic_skill_name", "직업기초능력명", "name"),
                )
            )
