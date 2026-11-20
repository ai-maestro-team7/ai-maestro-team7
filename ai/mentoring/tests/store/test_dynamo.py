from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

from mentoring.models import (
    CareerProfile,
    DocumentLatest,
    DocumentSource,
    DocumentType,
    DocumentVersion,
    ExtractionStatus,
    Task,
    TaskStatus,
    TaskType,
)
from mentoring.ports import AlreadyExists, VersionConflict
from mentoring.store.dynamo import DynamoUserRepo
from mentoring.store.memory import MemoryUserRepo


def _document():
    version = DocumentVersion(
        document_id="doc-0001",
        version=1,
        owner_user_id="user-1",
        document_type=DocumentType.RESUME,
        source=DocumentSource.TEXT,
        extraction_status=ExtractionStatus.EXTRACTED,
        created_at="2026-11-20T10:00:00+09:00",
        updated_at="2026-11-20T10:00:00+09:00",
    )
    return DocumentLatest.of(version, version.created_at), version


def _profile(version=1):
    return CareerProfile(
        profile_id="profile-1",
        profile_version=version,
        owner_user_id="user-1",
        created_by="EXTRACTION",
        created_at="2026-11-20T10:00:00+09:00",
    )


def _task(status=TaskStatus.PENDING):
    return Task(
        task_id="task-1",
        task_type=TaskType.PROFILE_EXTRACT,
        status=status,
        owner_user_id="user-1",
        resource_id="doc-0001",
        resource_version=1,
        created_at="2026-11-20T10:00:00+09:00",
        updated_at="2026-11-20T10:00:01+09:00",
    )


@pytest.fixture
def table():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="ap-northeast-2")
        value = resource.create_table(
            TableName="test-career-mentor",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        yield value


def test_document_create_save_and_duplicate(table):
    repo = DynamoUserRepo(table)
    latest, version = _document()
    repo.create_document(latest, version)
    assert repo.get_document_latest("user-1", "doc-0001") == latest
    assert repo.get_document_version("user-1", "doc-0001", 1) == version
    with pytest.raises(AlreadyExists):
        repo.create_document(latest, version)

    changed = version.model_copy(update={"extraction_status": ExtractionStatus.COMPLETED})
    repo.save_document(DocumentLatest.of(changed, version.created_at), changed)
    assert repo.get_document_version("user-1", "doc-0001", 1).extraction_status == ExtractionStatus.COMPLETED


def test_profile_version_condition(table):
    repo = DynamoUserRepo(table)
    repo.put_profile_version(_profile(1), expected_version=None)
    repo.put_profile_version(_profile(2), expected_version=1)
    assert repo.get_profile_pointer("user-1").latest_version == 2
    with pytest.raises(VersionConflict):
        repo.put_profile_version(_profile(3), expected_version=1)


def test_task_condition_and_gsi(table):
    repo = DynamoUserRepo(table)
    repo.create_task(_task())
    with pytest.raises(AlreadyExists):
        repo.create_task(_task())
    completed = _task(TaskStatus.COMPLETED)
    assert not repo.update_task(completed, expected_status=TaskStatus.PROCESSING)
    assert repo.update_task(completed, expected_status=TaskStatus.PENDING)
    item = table.get_item(Key={"PK": "USER#user-1", "SK": "TASK#task-1"})["Item"]
    assert item["GSI1PK"] == "TASK#COMPLETED"
    assert item["GSI1SK"].endswith("#user-1#task-1")


def test_idempotency_states_and_numeric_ttl(table):
    repo = DynamoUserRepo(table)
    expires = "2026-11-21T00:00:00+00:00"
    assert repo.idem_begin("user-1", "idem-1", "hash-a", expires).state == "NEW"
    item = table.get_item(Key={"PK": "USER#user-1", "SK": "IDEM#idem-1"})["Item"]
    assert item["expiresAt"] == int(datetime.fromisoformat(expires).timestamp())
    repo.idem_complete("user-1", "idem-1", {"documentId": "doc-0001"})
    replay = repo.idem_begin("user-1", "idem-1", "hash-a", expires)
    assert replay.state == "REPLAY" and replay.result == {"documentId": "doc-0001"}
    assert repo.idem_begin("user-1", "idem-1", "hash-b", expires).state == "CONFLICT"


@pytest.mark.parametrize("repo_kind", ["memory", "dynamo"])
def test_same_public_results(table, repo_kind):
    repo = MemoryUserRepo() if repo_kind == "memory" else DynamoUserRepo(table)
    latest, version = _document()
    repo.create_document(latest, version)
    repo.create_task(_task())
    repo.put_profile_version(_profile(), expected_version=None)
    assert repo.get_document_latest("user-1", "doc-0001") == latest
    assert repo.get_task("user-1", "task-1") == _task()
    assert repo.get_profile_version("user-1", "profile-1", 1) == _profile()
