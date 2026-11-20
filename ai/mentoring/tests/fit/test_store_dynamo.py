"""적합도 분석 DynamoDB 저장소와 공고 읽기 (moto). 메모리 구현과 같은 키를 쓰는지 본다."""
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from mentoring.fit.records import JobFitAnalysis
from mentoring.fit.store import DynamoAnalysisStore, DynamoCatalogReader, MemoryAnalysisStore, analysis_item
from mentoring.models import TaskStatus
from mentoring.ports import AlreadyExists


def _table(name):
    client = boto3.client("dynamodb", region_name="ap-northeast-2")
    client.create_table(
        TableName=name, BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("PK", "SK", "GSI1PK", "GSI1SK")],
        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
        GlobalSecondaryIndexes=[{"IndexName": "GSI1", "Projection": {"ProjectionType": "ALL"},
                                 "KeySchema": [{"AttributeName": "GSI1PK", "KeyType": "HASH"},
                                               {"AttributeName": "GSI1SK", "KeyType": "RANGE"}]}],
    )
    return boto3.resource("dynamodb", region_name="ap-northeast-2").Table(name)


def _analysis(**changes):
    data = dict(analysis_id="analysis-1", owner_user_id="user-1", status=TaskStatus.PENDING, task_id="task-1",
                assessment_mode="POSTING", profile_id="profile-1", profile_version=1, workspace_id="ws-1",
                job_posting_id="job-1", snapshot_id="20261120-aaaaaaaa", fit_score=81, potential_upper_bound=81,
                created_at="2026-11-21T10:00:00+09:00", updated_at="2026-11-21T10:00:00+09:00")
    data.update(changes)
    return JobFitAnalysis(**data)


@mock_aws
def test_dynamo_analysis_store_round_trip_and_workspace_index():
    table = _table("team07-career-mentor")
    store = DynamoAnalysisStore(table)
    store.create_analysis(_analysis())
    with pytest.raises(AlreadyExists):
        store.create_analysis(_analysis())
    store.save_analysis(_analysis(status=TaskStatus.COMPLETED))
    assert store.get_analysis("user-1", "analysis-1").status == TaskStatus.COMPLETED
    assert store.get_analysis("user-2", "analysis-1") is None
    item = table.get_item(Key={"PK": "USER#user-1", "SK": "ANALYSIS#analysis-1"})["Item"]
    assert item["GSI1PK"] == "USER#user-1#WS#ws-1"
    assert item == {**analysis_item(_analysis(status=TaskStatus.COMPLETED)), "fitScore": Decimal(81),
                    "potentialUpperBound": Decimal(81), "profileVersion": Decimal(1)}

    table.put_item(Item={"PK": "USER#user-1", "SK": "PROFILE#BASIC", "educationLevel": "BACHELOR",
                         "careerYears": Decimal(0)})
    assert store.get_basic_profile("user-1")["careerYears"] == 0
    assert store.get_basic_profile("user-2") is None


@mock_aws
def test_dynamo_catalog_reader_reads_latest_and_snapshot_with_plain_numbers():
    table = _table("team07-catalog")
    table.put_item(Item={"PK": "POSTING#job-1", "SK": "LATEST", "jobPostingId": "job-1",
                         "snapshotId": "20261120-aaaaaaaa", "isExpired": False})
    table.put_item(Item={"PK": "POSTING#job-1", "SK": "SNAP#20261120-aaaaaaaa", "jobPostingId": "job-1",
                         "snapshotId": "20261120-aaaaaaaa", "title": "가상", "organization": "가상 회사",
                         "requirements": [{"requirementId": "req-1", "name": "SQL", "kind": "REQUIRED_SKILL",
                                           "weight": Decimal("1.5")}]})
    reader = DynamoCatalogReader(table)
    assert reader.get_latest("job-1")["snapshotId"] == "20261120-aaaaaaaa"
    assert reader.get_snapshot("job-1", "20261120-aaaaaaaa")["requirements"][0]["weight"] == 1.5
    assert reader.get_latest("job-2") is None


def test_memory_store_uses_same_item_shape():
    store = MemoryAnalysisStore()
    store.create_analysis(_analysis())
    assert store.items[("USER#user-1", "ANALYSIS#analysis-1")] == analysis_item(_analysis())
