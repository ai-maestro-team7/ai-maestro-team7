"""사용자 결과 항목 저장소 (첨삭 `REVIEW#`, 학습 경로 `PATH#`, db-schema §2.1)와 시험일정 캐시 읽기.

- 결과: `team07-career-mentor` PK `USER#{userId}` / SK `{접두사}#{id}`. 워크스페이스가 있으면
  GSI1 `USER#{u}#WS#{wsId}` / `{접두사}#{createdAt}#{id}` (docs/api.md §6.0)
- 시험일정: `team07-cache` 키 `cache_key = EXAM#{qualificationCode}#{year}` (#95 수집, 읽기만)
GetItem만 쓴다.
"""
from __future__ import annotations

from typing import Any

from mentoring.ports import AlreadyExists

from ..fit.store import _decimal, plain


def result_item(prefix: str, entity_type: str, record, rid: str) -> dict:
    data = record.to_api()
    item = {**data, "PK": f"USER#{record.owner_user_id}", "SK": f"{prefix}#{rid}", "entityType": entity_type,
            "ownerUserId": record.owner_user_id}
    if getattr(record, "workspace_id", None):
        item["GSI1PK"] = f"USER#{record.owner_user_id}#WS#{record.workspace_id}"
        item["GSI1SK"] = f"{prefix}#{record.created_at}#{rid}"
    return item


class MemoryResultStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def create(self, item: dict) -> None:
        key = (item["PK"], item["SK"])
        if key in self.items:
            raise AlreadyExists(item["SK"])
        self.items[key] = dict(item)

    def save(self, item: dict) -> None:
        self.items[(item["PK"], item["SK"])] = dict(item)

    def get(self, user_id: str, sk: str) -> dict | None:
        item = self.items.get((f"USER#{user_id}", sk))
        return dict(item) if item else None


class DynamoResultStore:
    def __init__(self, table: Any) -> None:
        self._table = table

    def create(self, item: dict) -> None:
        from botocore.exceptions import ClientError

        try:
            self._table.put_item(Item=_decimal(item), ConditionExpression="attribute_not_exists(PK)")
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise AlreadyExists(item["SK"]) from error
            raise

    def save(self, item: dict) -> None:
        self._table.put_item(Item=_decimal(item))

    def get(self, user_id: str, sk: str) -> dict | None:
        item = self._table.get_item(Key={"PK": f"USER#{user_id}", "SK": sk}).get("Item")
        return plain(item) if item else None


class MemoryExamSchedules:
    """테스트용: #95가 수집해 둔 시험일정 캐시를 흉내 낸다."""

    def __init__(self) -> None:
        self.items: dict[str, dict] = {}

    def put(self, code: str, year: int, items: list[dict], *, collected_at: str, expires_at: int,
            source_url: str = "https://apis.data.go.kr/B490007/qualExamSchd/getQualExamSchdList") -> None:
        self.items[f"EXAM#{code}#{year}"] = {"cache_key": f"EXAM#{code}#{year}", "qualificationCode": code,
                                             "year": year, "items": items, "sourceUrl": source_url,
                                             "collectedAt": collected_at, "expires_at": expires_at}

    def get(self, code: str, year: int) -> dict | None:
        item = self.items.get(f"EXAM#{code}#{year}")
        return dict(item) if item else None


class DynamoExamSchedules:
    def __init__(self, table: Any) -> None:
        self._table = table

    def get(self, code: str, year: int) -> dict | None:
        item = self._table.get_item(Key={"cache_key": f"EXAM#{code}#{year}"}).get("Item")
        return plain(item) if item else None
