import boto3
import pytest
from moto import mock_aws

from mentoring.ports import AlreadyExists, VersionConflict
from mentoring.stories.dynamo import DynamoStoryRepo
from mentoring.stories.memory import MemoryStoryRepo
from mentoring.stories.models import StoryLatest, StoryVersion


def _story(version=1, *, status="DRAFT"):
    return StoryVersion(
        story_id="story-1",
        version=version,
        owner_user_id="user-1",
        status=status,
        raw_experience="가상 프로젝트에서 고객 인터뷰를 진행했습니다.",
        created_at="2026-11-20T10:00:00+09:00",
        updated_at=f"2026-11-20T10:00:0{version}+09:00",
    )


@pytest.fixture
def table():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="ap-northeast-2")
        yield resource.create_table(
            TableName="story-test",
            KeySchema=[{"AttributeName": "PK", "KeyType": "HASH"}, {"AttributeName": "SK", "KeyType": "RANGE"}],
            AttributeDefinitions=[{"AttributeName": "PK", "AttributeType": "S"}, {"AttributeName": "SK", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


@pytest.mark.parametrize("kind", ["memory", "dynamo"])
def test_memory_and_dynamo_have_same_versioned_result(table, kind):
    repo = MemoryStoryRepo() if kind == "memory" else DynamoStoryRepo(table)
    first = _story()
    repo.create_story(StoryLatest.of(first), first)
    second = _story(2, status="QUESTIONS_READY")
    repo.put_story_version(StoryLatest.of(second), second, expected_version=1)
    assert repo.get_latest("user-1", "story-1") == StoryLatest.of(second)
    assert repo.get_version("user-1", "story-1", 1) == first
    assert repo.get_version("user-1", "story-1", 2) == second
    assert repo.list_latest("user-1") == [StoryLatest.of(second)]
    assert repo.list_latest("user-2") == []


@pytest.mark.parametrize("kind", ["memory", "dynamo"])
def test_duplicate_and_version_conflict(table, kind):
    repo = MemoryStoryRepo() if kind == "memory" else DynamoStoryRepo(table)
    first = _story()
    repo.create_story(StoryLatest.of(first), first)
    with pytest.raises(AlreadyExists):
        repo.create_story(StoryLatest.of(first), first)
    second = _story(2)
    with pytest.raises(VersionConflict):
        repo.put_story_version(StoryLatest.of(second), second, expected_version=7)
