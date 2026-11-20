"""첨삭·학습 경로 결과 저장소와 시험일정 캐시 읽기 (moto). 메모리 구현과 같은 키를 쓰는지 본다."""
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

from mentoring.learning.models import LearningPathRecord
from mentoring.models import TaskStatus
from mentoring.ports import AlreadyExists
from mentoring.store.results import DynamoExamSchedules, DynamoResultStore, MemoryResultStore, result_item


def _record(**changes):
    data = dict(learning_path_id="path-1", owner_user_id="user-1", status=TaskStatus.PENDING, task_id="task-1",
                analysis_id="analysis-1", workspace_id="ws-1", weekly_study_hours=8, preferred_format="HYBRID",
                start_date="2026-11-21", created_at="2026-11-21T10:00:00+09:00",
                updated_at="2026-11-21T10:00:00+09:00")
    data.update(changes)
    return LearningPathRecord(**data)


@mock_aws
def test_dynamo_result_store_round_trip_and_workspace_index():
    client = boto3.client("dynamodb", region_name="ap-northeast-2")
    client.create_table(TableName="t", BillingMode="PAY_PER_REQUEST",
                        AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"},
                                              {"AttributeName": "SK", "AttributeType": "S"}],
                        KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"},
                                   {"AttributeName": "SK", "KeyType": "RANGE"}])
    store = DynamoResultStore(boto3.resource("dynamodb", region_name="ap-northeast-2").Table("t"))
    item = result_item("PATH", "LEARNING_PATH", _record(), "path-1")
    store.create(item)
    with pytest.raises(AlreadyExists):
        store.create(item)
    store.save(result_item("PATH", "LEARNING_PATH", _record(status=TaskStatus.COMPLETED, total_hours=64), "path-1"))
    got = store.get("user-1", "PATH#path-1")
    assert got["status"] == "COMPLETED" and got["totalHours"] == 64 and not isinstance(got["totalHours"], Decimal)
    assert got["GSI1PK"] == "USER#user-1#WS#ws-1" and got["GSI1SK"].startswith("PATH#2026-11-21T10:00:00+09:00#")
    assert store.get("user-2", "PATH#path-1") is None

    memory = MemoryResultStore()
    memory.create(item)
    assert memory.get("user-1", "PATH#path-1") == item


@mock_aws
def test_dynamo_exam_schedules_reads_cache_key():
    client = boto3.client("dynamodb", region_name="ap-northeast-2")
    client.create_table(TableName="cache", BillingMode="PAY_PER_REQUEST",
                        AttributeDefinitions=[{"AttributeName": "cache_key", "AttributeType": "S"}],
                        KeySchema=[{"AttributeName": "cache_key", "KeyType": "HASH"}])
    table = boto3.resource("dynamodb", region_name="ap-northeast-2").Table("cache")
    table.put_item(Item={"cache_key": "EXAM#G521#2026", "items": [{"docPassDt": "20261215"}],
                         "collectedAt": "2026-11-21T06:00:00+09:00", "expires_at": Decimal(1800000000)})
    reader = DynamoExamSchedules(table)
    item = reader.get("G521", 2026)
    assert item["items"][0]["docPassDt"] == "20261215" and item["expires_at"] == 1800000000
    assert reader.get("G521", 2027) is None
