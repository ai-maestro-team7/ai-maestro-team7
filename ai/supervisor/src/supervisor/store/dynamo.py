"""`team07-career-mentor`의 `SESSION#`·`CHAT#` (db-schema §2.1 v1.4). 사용자 파티션 안에서 GetItem·Query만 쓴다."""

import json
from decimal import Decimal
from typing import Any

from ..models import ChatMessage, ChatSession

PENDING = "PENDING"


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _session_sk(session_id: str) -> str:
    return f"SESSION#{session_id}"


def _chat_prefix(session_id: str) -> str:
    return f"CHAT#{session_id}#"


def _to_dynamo(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False), parse_float=Decimal)


def _to_plain(value: Any) -> Any:
    if isinstance(value, list):
        return [_to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_plain(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def _conditional_failed(error: Exception) -> bool:
    response = getattr(error, "response", None) or {}
    return response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


class DynamoChatStore:
    def __init__(self, table: Any):
        self.table = table

    # ------------------------------------------------------------ 대화
    def get_session(self, user_id, session_id):
        item = self.table.get_item(Key={"PK": _pk(user_id), "SK": _session_sk(session_id)}, ConsistentRead=True).get("Item")
        return ChatSession.model_validate(_to_plain(item)) if item else None

    def create_session(self, session):
        item = {**session.to_api(), "PK": _pk(session.owner_user_id), "SK": _session_sk(session.session_id),
                "entityType": "ChatSession", "schemaVersion": "1.0"}
        self.table.put_item(Item=_to_dynamo(item), ConditionExpression="attribute_not_exists(PK)")

    def begin_turn(self, user_id, session_id, message_id, *, now, stale_before, max_messages):
        try:
            self.table.update_item(
                Key={"PK": _pk(user_id), "SK": _session_sk(session_id)},
                UpdateExpression="SET pendingMessageId = :mid, pendingSince = :now, lastMessageAt = :now "
                                 "ADD messageCount :two",
                ConditionExpression="attribute_exists(PK) AND (attribute_not_exists(messageCount) OR messageCount <= :room) "
                                    "AND (attribute_not_exists(pendingMessageId) OR pendingSince < :stale)",
                ExpressionAttributeValues={":mid": message_id, ":now": now, ":two": 2,
                                           ":room": max_messages - 2, ":stale": stale_before})
        except Exception as error:  # noqa: BLE001
            if _conditional_failed(error):
                return False
            raise
        return True

    def end_turn(self, user_id, session_id, message_id, *, now):
        try:
            self.table.update_item(
                Key={"PK": _pk(user_id), "SK": _session_sk(session_id)},
                UpdateExpression="REMOVE pendingMessageId, pendingSince SET lastMessageAt = :now",
                ConditionExpression="pendingMessageId = :mid",
                ExpressionAttributeValues={":mid": message_id, ":now": now})
        except Exception as error:  # noqa: BLE001
            if not _conditional_failed(error):
                raise

    # ------------------------------------------------------------ 메시지
    def put_message(self, message):
        item = {**message.to_api(), "PK": _pk(message.owner_user_id),
                "SK": f"{_chat_prefix(message.session_id)}{message.message_id}",
                "entityType": "ChatMessage", "schemaVersion": "1.0"}
        self.table.put_item(Item=_to_dynamo(item))

    def get_message(self, user_id, session_id, message_id):
        # 방금 쓴 메시지를 바로 읽는다 (claim 직후 작업자). 최종 일관 읽기면 못 찾고 턴을 건너뛸 수 있다
        item = self.table.get_item(Key={"PK": _pk(user_id), "SK": f"{_chat_prefix(session_id)}{message_id}"},
                                   ConsistentRead=True).get("Item")
        return ChatMessage.model_validate(_to_plain(item)) if item else None

    def list_messages(self, user_id, session_id, limit):
        from boto3.dynamodb.conditions import Key

        response = self.table.query(
            KeyConditionExpression=Key("PK").eq(_pk(user_id)) & Key("SK").begins_with(_chat_prefix(session_id)),
            ScanIndexForward=False, Limit=limit, ConsistentRead=True)
        items = [ChatMessage.model_validate(_to_plain(i)) for i in response.get("Items", [])]
        return list(reversed(items))

    def claim_message(self, user_id, session_id, message_id, *, now):
        try:
            self.table.update_item(
                Key={"PK": _pk(user_id), "SK": f"{_chat_prefix(session_id)}{message_id}"},
                UpdateExpression="SET #status = :processing, updatedAt = :now",
                ConditionExpression="attribute_exists(PK) AND #status = :pending",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":processing": "PROCESSING", ":pending": PENDING, ":now": now})
        except Exception as error:  # noqa: BLE001
            if _conditional_failed(error):
                return False
            raise
        return True
