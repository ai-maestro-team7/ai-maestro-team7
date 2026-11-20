from __future__ import annotations

import csv
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from mentoring.reference import CsvReferenceLookup, DynamoReferenceLookup, ReferenceLoader


def _write(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def structured(tmp_path: Path) -> Path:
    _write(
        tmp_path / "selected_job_profiles.csv",
        [{"ncs_subcategory_code": "20010105", "job_role": "가상 데이터 분석", "job_description": "가상 직무"}],
    )
    _write(
        tmp_path / "selected_competency_units.csv",
        [
            {
                "ncs_subcategory_code": "20010105",
                "competency_unit_code": "2001010501_00v1",
                "competency_unit_name": "가상 데이터 수집",
                "training_hours": "20",
                "source_reference_date": "2026-11-20",
            },
            {
                "ncs_subcategory_code": "20010105",
                "competency_unit_code": "2001010502_00v1",
                "competency_unit_name": "가상 데이터 분석",
                "training_hours": "30",
                "source_reference_date": "2026-11-20",
            },
        ],
    )
    qualification = {
        "competency_unit_code": "2001010501_00v1",
        "qualification_code": "VIRTUAL-Q1",
        "qualification_name": "가상 데이터 자격",
        "unit_type": "선택",
        "training_hours": "20",
    }
    duplicate = {**qualification, "training_hours": "999"}
    _write(tmp_path / "selected_qualification_links.csv", [qualification, duplicate])
    _write(
        tmp_path / "selected_ncs_classification.csv",
        [{"ncs_subcategory_code": "20010105", "ncs_subcategory_name": "가상 분석 분류"}],
    )
    _write(
        tmp_path / "ncs_basic_skills.csv",
        [{"skill_id": "COMM", "skill_name": "가상 의사소통"}],
    )
    return tmp_path


def _table():
    resource = boto3.resource("dynamodb", region_name="ap-northeast-2")
    return resource.create_table(
        TableName="virtual-reference",
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def test_csv_lookup_uses_exact_codes_and_deduplicates_links(structured: Path) -> None:
    lookup = CsvReferenceLookup(str(structured))

    assert lookup.get_job_profile("20010105").name == "가상 데이터 분석"
    assert lookup.get_job_profile("200101") is None
    assert [item.unit_code for item in lookup.list_units("20010105")] == [
        "2001010501_00v1",
        "2001010502_00v1",
    ]
    links = lookup.list_qualification_links("2001010501_00v1")
    assert len(links) == 1
    assert links[0].training_hours == 20


@mock_aws
def test_dry_run_does_not_write_and_two_loads_are_idempotent(structured: Path) -> None:
    table = _table()
    loader = ReferenceLoader(str(structured))

    dry_run = loader.load(table)
    assert dry_run.dry_run is True
    assert dry_run.written == 0
    assert table.scan()["Count"] == 0

    first = loader.load(table, write=True)
    count = table.scan()["Count"]
    second = loader.load(table, write=True)

    assert first.written == first.total
    assert second.total == first.total
    assert table.scan()["Count"] == count


@mock_aws
def test_csv_and_dynamo_lookup_return_same_results(structured: Path) -> None:
    table = _table()
    ReferenceLoader(str(structured)).load(table, write=True)
    csv_lookup = CsvReferenceLookup(str(structured))
    dynamo_lookup = DynamoReferenceLookup(table)

    assert dynamo_lookup.get_job_profile("20010105") == csv_lookup.get_job_profile("20010105")
    assert dynamo_lookup.find_job_profiles_by_name("가상 데이터 분석") == csv_lookup.find_job_profiles_by_name(
        "가상 데이터 분석"
    )
    assert dynamo_lookup.list_units("20010105") == csv_lookup.list_units("20010105")
    assert dynamo_lookup.get_unit("20010105", "2001010501_00v1") == csv_lookup.get_unit(
        "20010105", "2001010501_00v1"
    )
    assert dynamo_lookup.list_qualification_links(
        "2001010501_00v1"
    ) == csv_lookup.list_qualification_links("2001010501_00v1")
    assert dynamo_lookup.list_basic_skills() == csv_lookup.list_basic_skills()


@mock_aws
def test_table_name_is_required_from_environment() -> None:
    resource = boto3.resource("dynamodb", region_name="ap-northeast-2")

    with pytest.raises(RuntimeError, match="TABLE_REFERENCE"):
        DynamoReferenceLookup.from_environment(resource, {})


def test_rejects_non_utf8_csv(structured: Path) -> None:
    (structured / "selected_job_profiles.csv").write_bytes("가상".encode("cp949"))

    with pytest.raises(ValueError, match="UTF-8"):
        CsvReferenceLookup(str(structured))
