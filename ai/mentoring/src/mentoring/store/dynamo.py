"""DynamoDB implementation of the mentoring user repository."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from botocore.exceptions import ClientError

from mentoring.models import CareerProfile, DocumentLatest, DocumentVersion, ProfilePointer, Task, TaskStatus
from mentoring.ports import AlreadyExists, IdemResult, VersionConflict


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _decimal(value: Any) -> Any:
    """Convert floats recursively because DynamoDB rejects binary floats."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimal(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal(item) for item in value]
    return value


def _is_conditional(error: ClientError) -> bool:
    code = error.response.get("Error", {}).get("Code")
    if code == "ConditionalCheckFailedException":
        return True
    if code != "TransactionCanceledException":
        return False
    return any(
        reason.get("Code") == "ConditionalCheckFailed"
        for reason in error.response.get("CancellationReasons", [])
    )


class DynamoUserRepo:
    """User-scoped repository. It never scans the table."""

    def __init__(self, table: Any) -> None:
        self._table = table
        self._client = table.meta.client
        self._table_name = table.name

    @staticmethod
    def _item(model: Any, sk: str, entity_type: str) -> dict[str, Any]:
        data = model.to_api()
        return _decimal(
            {
                **data,
                "PK": _pk(model.owner_user_id),
                "SK": sk,
                "entityType": entity_type,
                "ownerUserId": model.owner_user_id,
            }
        )

    def _put_tx(self, item: dict[str, Any], *, condition: str | None = None) -> dict[str, Any]:
        # A Table resource client has DynamoDB's native-value transformer installed,
        # including for TransactWriteItems.
        request: dict[str, Any] = {"TableName": self._table_name, "Item": _decimal(item)}
        if condition:
            request["ConditionExpression"] = condition
        return {"Put": request}

    def _get(self, user_id: str, sk: str) -> dict[str, Any] | None:
        return self._table.get_item(Key={"PK": _pk(user_id), "SK": sk}).get("Item")

    def create_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        items = [
            self._put_tx(
                self._item(latest, f"DOC_LATEST#{latest.document_id}", "DOCUMENT_LATEST"),
                condition="attribute_not_exists(PK)",
            ),
            self._put_tx(
                self._item(version, f"DOC#{version.document_id}#V#{version.version:04d}", "DOCUMENT_VERSION"),
                condition="attribute_not_exists(PK)",
            ),
        ]
        try:
            self._client.transact_write_items(TransactItems=items)
        except ClientError as error:
            if _is_conditional(error):
                raise AlreadyExists(latest.document_id) from error
            raise

    def save_document(self, latest: DocumentLatest, version: DocumentVersion) -> None:
        self._client.transact_write_items(
            TransactItems=[
                self._put_tx(self._item(latest, f"DOC_LATEST#{latest.document_id}", "DOCUMENT_LATEST")),
                self._put_tx(
                    self._item(version, f"DOC#{version.document_id}#V#{version.version:04d}", "DOCUMENT_VERSION")
                ),
            ]
        )

    def get_document_latest(self, user_id: str, document_id: str) -> DocumentLatest | None:
        item = self._get(user_id, f"DOC_LATEST#{document_id}")
        return DocumentLatest.model_validate(item) if item else None

    def get_document_version(self, user_id: str, document_id: str, version: int) -> DocumentVersion | None:
        item = self._get(user_id, f"DOC#{document_id}#V#{version:04d}")
        return DocumentVersion.model_validate(item) if item else None

    def get_profile_pointer(self, user_id: str) -> ProfilePointer | None:
        item = self._get(user_id, "PROFILE#LATEST")
        return ProfilePointer.model_validate(item) if item else None

    def get_profile_version(self, user_id: str, profile_id: str, version: int) -> CareerProfile | None:
        item = self._get(user_id, f"PROFILE#{profile_id}#V#{version:04d}")
        return CareerProfile.model_validate(item) if item else None

    def put_profile_version(self, profile: CareerProfile, *, expected_version: int | None) -> None:
        version_sk = f"PROFILE#{profile.profile_id}#V#{profile.profile_version:04d}"
        pointer = ProfilePointer(
            owner_user_id=profile.owner_user_id,
            latest_profile_id=profile.profile_id,
            latest_version=profile.profile_version,
        )
        pointer_request = self._put_tx(self._item(pointer, "PROFILE#LATEST", "PROFILE_LATEST"))
        put = pointer_request["Put"]
        if expected_version is None:
            put["ConditionExpression"] = "attribute_not_exists(PK)"
        else:
            put["ConditionExpression"] = "latestVersion = :expected"
            put["ExpressionAttributeValues"] = {":expected": expected_version}
        try:
            self._client.transact_write_items(
                TransactItems=[
                    self._put_tx(
                        self._item(profile, version_sk, "PROFILE_VERSION"),
                        condition="attribute_not_exists(PK)",
                    ),
                    pointer_request,
                ]
            )
        except ClientError as error:
            if _is_conditional(error):
                raise VersionConflict(f"profile version conflict: {profile.profile_version}") from error
            raise

    @staticmethod
    def _task_item(task: Task) -> dict[str, Any]:
        item = DynamoUserRepo._item(task, f"TASK#{task.task_id}", "TASK")
        item["GSI1PK"] = f"TASK#{task.status.value}"
        item["GSI1SK"] = f"{task.updated_at}#{task.owner_user_id}#{task.task_id}"
        return item

    def create_task(self, task: Task) -> None:
        try:
            self._table.put_item(
                Item=self._task_item(task),
                ConditionExpression="attribute_not_exists(PK)",
            )
        except ClientError as error:
            if _is_conditional(error):
                raise AlreadyExists(task.task_id) from error
            raise

    def get_task(self, user_id: str, task_id: str) -> Task | None:
        item = self._get(user_id, f"TASK#{task_id}")
        return Task.model_validate(item) if item else None

    def update_task(self, task: Task, *, expected_status: TaskStatus) -> bool:
        try:
            self._table.put_item(
                Item=self._task_item(task),
                ConditionExpression="#status = :expected",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":expected": expected_status.value},
            )
        except ClientError as error:
            if _is_conditional(error):
                return False
            raise
        return True

    def idem_begin(self, user_id: str, key: str, request_hash: str, expires_at: str) -> IdemResult:
        item = {
            "PK": _pk(user_id),
            "SK": f"IDEM#{key}",
            "entityType": "IDEMPOTENCY",
            "ownerUserId": user_id,
            "requestHash": request_hash,
            "result": None,
            "expiresAt": int(datetime.fromisoformat(expires_at.replace("Z", "+00:00")).timestamp()),
        }
        try:
            self._table.put_item(Item=item, ConditionExpression="attribute_not_exists(PK)")
            return IdemResult("NEW")
        except ClientError as error:
            if not _is_conditional(error):
                raise
        stored = self._get(user_id, f"IDEM#{key}") or {}
        if stored.get("requestHash") != request_hash:
            return IdemResult("CONFLICT")
        return IdemResult("REPLAY", stored.get("result"))

    def idem_complete(self, user_id: str, key: str, result: dict) -> None:
        self._table.update_item(
            Key={"PK": _pk(user_id), "SK": f"IDEM#{key}"},
            UpdateExpression="SET #result = :result",
            ExpressionAttributeNames={"#result": "result"},
            ExpressionAttributeValues={":result": _decimal(result)},
        )
