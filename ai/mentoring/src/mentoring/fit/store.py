"""적합도 분석 저장소와 공고 읽기. 메모리 구현(테스트)과 DynamoDB 구현(운영)이 같은 키를 쓴다.

- 분석: `team07-career-mentor` PK `USER#{userId}` / SK `ANALYSIS#{analysisId}`.
  워크스페이스가 있으면 GSI1 `USER#{u}#WS#{wsId}` / `ANALYSIS#{createdAt}#{id}` (docs/api.md §6.0)
- 기본 프로필: 같은 테이블 `PROFILE#BASIC` (읽기만)
- 공고: `team07-catalog` PK `POSTING#{id}` / SK `LATEST`·`SNAP#{snapshotId}` (읽기만)
GetItem만 쓴다. Scan은 쓰지 않는다.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from mentoring.ports import AlreadyExists

from .records import JobFitAnalysis


def _pk(user_id: str) -> str:
    return f"USER#{user_id}"


def _sk(analysis_id: str) -> str:
    return f"ANALYSIS#{analysis_id}"


def plain(value: Any) -> Any:
    """DynamoDB Decimal → int/float (읽기)."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item) for item in value]
    return value


def _decimal(value: Any) -> Any:
    """float → Decimal (쓰기). DynamoDB는 float를 받지 않는다."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _decimal(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decimal(item) for item in value]
    return value


def analysis_item(analysis: JobFitAnalysis) -> dict:
    item = {**analysis.to_api(), "PK": _pk(analysis.owner_user_id), "SK": _sk(analysis.analysis_id),
            "entityType": "ANALYSIS", "ownerUserId": analysis.owner_user_id}
    if analysis.workspace_id:
        item["GSI1PK"] = f"USER#{analysis.owner_user_id}#WS#{analysis.workspace_id}"
        item["GSI1SK"] = f"ANALYSIS#{analysis.created_at}#{analysis.analysis_id}"
    return item


# ---------------------------------------------------------------- 메모리
class MemoryAnalysisStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def create_analysis(self, analysis: JobFitAnalysis) -> None:
        key = (_pk(analysis.owner_user_id), _sk(analysis.analysis_id))
        if key in self.items:
            raise AlreadyExists(analysis.analysis_id)
        self.items[key] = analysis_item(analysis)

    def save_analysis(self, analysis: JobFitAnalysis) -> None:
        self.items[(_pk(analysis.owner_user_id), _sk(analysis.analysis_id))] = analysis_item(analysis)

    def get_analysis(self, user_id: str, analysis_id: str) -> JobFitAnalysis | None:
        item = self.items.get((_pk(user_id), _sk(analysis_id)))
        return JobFitAnalysis.model_validate(item) if item else None

    def get_basic_profile(self, user_id: str) -> dict | None:
        item = self.items.get((_pk(user_id), "PROFILE#BASIC"))
        return dict(item) if item else None

    def put_basic_profile(self, user_id: str, profile: dict) -> None:
        """테스트용: 백엔드가 온보딩에서 쓴 기본 프로필을 흉내 낸다."""
        self.items[(_pk(user_id), "PROFILE#BASIC")] = {**profile, "PK": _pk(user_id), "SK": "PROFILE#BASIC"}


class MemoryCatalog:
    """테스트용 catalog. `put_posting`으로 B가 저장한 공고를 흉내 낸다."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def put_posting(self, snapshot: dict, *, is_expired: bool = False) -> None:
        pk = f"POSTING#{snapshot['jobPostingId']}"
        self.items[(pk, f"SNAP#{snapshot['snapshotId']}")] = dict(snapshot)
        self.items[(pk, "LATEST")] = {"jobPostingId": snapshot["jobPostingId"], "snapshotId": snapshot["snapshotId"],
                                      "isExpired": is_expired}

    def get_latest(self, job_posting_id: str) -> dict | None:
        item = self.items.get((f"POSTING#{job_posting_id}", "LATEST"))
        return dict(item) if item else None

    def get_snapshot(self, job_posting_id: str, snapshot_id: str) -> dict | None:
        item = self.items.get((f"POSTING#{job_posting_id}", f"SNAP#{snapshot_id}"))
        return dict(item) if item else None


# ---------------------------------------------------------------- DynamoDB
class DynamoAnalysisStore:
    def __init__(self, table: Any) -> None:
        self._table = table

    def create_analysis(self, analysis: JobFitAnalysis) -> None:
        from botocore.exceptions import ClientError

        try:
            self._table.put_item(Item=_decimal(analysis_item(analysis)),
                                 ConditionExpression="attribute_not_exists(PK)")
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise AlreadyExists(analysis.analysis_id) from error
            raise

    def save_analysis(self, analysis: JobFitAnalysis) -> None:
        self._table.put_item(Item=_decimal(analysis_item(analysis)))

    def get_analysis(self, user_id: str, analysis_id: str) -> JobFitAnalysis | None:
        item = self._table.get_item(Key={"PK": _pk(user_id), "SK": _sk(analysis_id)}).get("Item")
        return JobFitAnalysis.model_validate(plain(item)) if item else None

    def get_basic_profile(self, user_id: str) -> dict | None:
        item = self._table.get_item(Key={"PK": _pk(user_id), "SK": "PROFILE#BASIC"}).get("Item")
        return plain(item) if item else None


class DynamoCatalogReader:
    def __init__(self, table: Any) -> None:
        self._table = table

    def _get(self, pk: str, sk: str) -> dict | None:
        item = self._table.get_item(Key={"PK": pk, "SK": sk}).get("Item")
        return plain(item) if item else None

    def get_latest(self, job_posting_id: str) -> dict | None:
        return self._get(f"POSTING#{job_posting_id}", "LATEST")

    def get_snapshot(self, job_posting_id: str, snapshot_id: str) -> dict | None:
        return self._get(f"POSTING#{job_posting_id}", f"SNAP#{snapshot_id}")
