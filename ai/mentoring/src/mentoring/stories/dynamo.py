"""DynamoDB Story Bank implementation. It uses GetItem, Query, and transactions only."""
from typing import Any

from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from mentoring.ports import AlreadyExists, VersionConflict

from .models import StoryLatest, StoryVersion


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _conditional(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code")
    return code == "ConditionalCheckFailedException" or (
        code == "TransactionCanceledException"
        and any(
            reason.get("Code") == "ConditionalCheckFailed"
            for reason in error.response.get("CancellationReasons", [])
        )
    )


class DynamoStoryRepo:
    def __init__(self, table: Any) -> None:
        self._table = table
        self._client = table.meta.client

    @staticmethod
    def _item(model: StoryLatest | StoryVersion, sk: str, entity_type: str) -> dict:
        return {
            **model.to_api(),
            "PK": _pk(model.owner_user_id),
            "SK": sk,
            "entityType": entity_type,
            "ownerUserId": model.owner_user_id,
        }

    def _put(self, item: dict, condition: str, values: dict | None = None) -> dict:
        put = {
            "TableName": self._table.name,
            "Item": item,
            "ConditionExpression": condition,
        }
        if values:
            put["ExpressionAttributeValues"] = values
        return {"Put": put}

    def create_story(self, latest: StoryLatest, version: StoryVersion) -> None:
        try:
            self._client.transact_write_items(
                TransactItems=[
                    self._put(
                        self._item(latest, f"STORY_LATEST#{latest.story_id}", "STORY_LATEST"),
                        "attribute_not_exists(PK)",
                    ),
                    self._put(
                        self._item(version, f"STORY#{version.story_id}#V#{version.version:04d}", "STORY_VERSION"),
                        "attribute_not_exists(PK)",
                    ),
                ]
            )
        except ClientError as error:
            if _conditional(error):
                raise AlreadyExists(latest.story_id) from error
            raise

    def put_story_version(
        self,
        latest: StoryLatest,
        version: StoryVersion,
        *,
        expected_version: int,
    ) -> None:
        try:
            self._client.transact_write_items(
                TransactItems=[
                    self._put(
                        self._item(version, f"STORY#{version.story_id}#V#{version.version:04d}", "STORY_VERSION"),
                        "attribute_not_exists(PK)",
                    ),
                    self._put(
                        self._item(latest, f"STORY_LATEST#{latest.story_id}", "STORY_LATEST"),
                        "latestVersion = :expected",
                        {":expected": expected_version},
                    ),
                ]
            )
        except ClientError as error:
            if _conditional(error):
                raise VersionConflict(f"expected {expected_version}") from error
            raise

    def get_latest(self, user_id: str, story_id: str) -> StoryLatest | None:
        item = self._table.get_item(
            Key={"PK": _pk(user_id), "SK": f"STORY_LATEST#{story_id}"}
        ).get("Item")
        return StoryLatest.model_validate(item) if item else None

    def get_version(self, user_id: str, story_id: str, version: int) -> StoryVersion | None:
        item = self._table.get_item(
            Key={"PK": _pk(user_id), "SK": f"STORY#{story_id}#V#{version:04d}"}
        ).get("Item")
        return StoryVersion.model_validate(item) if item else None

    def list_latest(self, user_id: str) -> list[StoryLatest]:
        items = self._table.query(
            KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with("STORY_LATEST#")
        ).get("Items", [])
        values = [StoryLatest.model_validate(item) for item in items]
        return sorted(values, key=lambda item: (item.updated_at, item.story_id), reverse=True)
