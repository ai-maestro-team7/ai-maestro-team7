"""DynamoDB 구현. `docs/db-schema.md` §2.2·§3의 키 구조를 따른다.

- `DynamoCatalog`: `team07-catalog` (공고·정책·기업). 읽기는 모두, 쓰기는 수집·보강 배치만 한다.
- `DynamoUsers`: `team07-career-mentor` (PK=`USER#{userId}`). 공통 프로필은 읽기만 한다.

규칙
- Scan은 쓰지 않는다. GetItem, Query, BatchGetItem만 쓴다.
- 모든 아이템에 `entityType`, `schemaVersion`, `createdAt`, `updatedAt`을 넣는다. 사용자 아이템에는 `ownerUserId`도 넣는다.
- 조건 없는 쓰기는 UpdateItem으로 해서 `createdAt`을 처음 값 그대로 둔다. 모델에서 값이 사라진 칸은 지운다.
- float은 Decimal로 바꿔 쓰고 읽을 때 되돌린다. 모델 ↔ 아이템은 `to_api()`와 `model_validate`다.
- 조건 실패는 False로 돌려주고, 그 밖의 boto3 오류는 `aws_service_error`로 바꾼다. 오류 메시지에 키나 개인정보를 넣지 않는다.
"""

import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from ..config import require_env
from ..core import clock
from ..models.errors import aws_service_error, invalid_input
from ..models.policy import Policy
from ..models.posting import AltCandidates, CompanyRecord, PostingLatest, PostingSnapshot
from ..models.profile import BasicProfile, OppPrefs
from ..models.user_state import ExplanationCache, Notification, PolicyAlert, SavedItem
from ..ports import IdemResult

SCHEMA_VERSION = "1.0"
GSI1 = "GSI1"
IDEM_TTL_HOURS = 24   # db-schema §2.2. 설정 파일에 없는 값이라 상수로 둔다
CAP_TTL_WEEKS = 2     # db-schema §2.2 (OPP#CAP# 2주)
BATCH_GET_LIMIT = 100  # BatchGetItem 한 번에 읽을 수 있는 키 수
NOT_EXISTS = "attribute_not_exists(SK)"

_CONDITIONAL = "ConditionalCheckFailedException"  # 단일 쓰기의 오류 코드
_TX_CONDITIONAL = "ConditionalCheckFailed"          # 트랜잭션 취소 사유 코드


# ---------------------------------------------------------------- 공통 도우미
class ConditionFailed(Exception):
    """조건부 쓰기의 조건이 어긋났다. 안쪽에서만 쓰고, 바깥으로는 False로 바꿔 내보낸다."""


@contextmanager
def aws_errors(service: str, *, conditional: bool = False):
    """boto3 오류를 `aws_service_error(service)`로 바꾼다. 원인은 `__cause__`에만 둔다.

    conditional=True면 조건 실패(ConditionalCheckFailed)는 `ConditionFailed`로 따로 올린다.
    다른 store 모듈도 같은 규칙으로 쓴다.
    """
    try:
        yield
    except ClientError as e:
        if conditional and _is_condition_failure(e):
            raise ConditionFailed from e
        raise aws_service_error(service) from e
    except BotoCoreError as e:
        raise aws_service_error(service) from e


def error_code(e: ClientError) -> str:
    return e.response.get("Error", {}).get("Code", "")


def _is_condition_failure(e: ClientError) -> bool:
    """조건 실패인가. 트랜잭션은 TransactionCanceledException으로 오고, 사유 목록에 ConditionalCheckFailed가 든다."""
    code = error_code(e)
    if code == _CONDITIONAL:
        return True
    if code != "TransactionCanceledException":
        return False
    reasons = e.response.get("CancellationReasons")
    if reasons:
        return any(r.get("Code") == _TX_CONDITIONAL for r in reasons)
    return _TX_CONDITIONAL in e.response.get("Error", {}).get("Message", "")


def to_ddb(value: Any) -> Any:
    """DynamoDB에 쓸 값. float → Decimal, 안쪽 dict·list도 바꾼다."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_ddb(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_ddb(v) for v in value]
    return value


def from_ddb(value: Any) -> Any:
    """읽은 값. Decimal → 정수면 int, 아니면 float."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: from_ddb(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_ddb(v) for v in value]
    return value


def _aliases(model_type) -> set[str]:
    """모델의 JSON(카멜) 키 전부. 값이 None이 된 칸을 지울 때 쓴다."""
    return {field.alias or name for name, field in model_type.model_fields.items()}


def _epoch(value: str | datetime) -> int:
    return int(clock.parse_as_of(value).timestamp())


class _Table:
    """테이블 하나에 대한 얇은 도우미. 위의 규칙(메타 칸, createdAt 보존, 조건부 쓰기)을 한곳에 둔다."""

    def __init__(self, resource, table_name: str, *, service: str, now: Callable[[], datetime]):
        self.resource = resource
        self.name = table_name
        self.table = resource.Table(table_name)
        self.service = service
        self.now = now

    def stamp(self) -> str:
        return clock.iso(self.now())

    # -- 읽기
    def get(self, pk: str, sk: str, *, consistent: bool = False) -> dict | None:
        with aws_errors(self.service):
            item = self.table.get_item(Key={"PK": pk, "SK": sk}, ConsistentRead=consistent).get("Item")
        return from_ddb(item) if item else None

    def query(self, **kwargs) -> Iterator[dict]:
        """Query 결과를 페이지 끝까지 돌려준다. 호출하는 쪽이 필요한 만큼만 읽고 멈출 수 있다."""
        start = None
        while True:
            params = dict(kwargs)
            if start:
                params["ExclusiveStartKey"] = start
            with aws_errors(self.service):
                page = self.table.query(**params)
            for item in page.get("Items", []):
                yield from_ddb(item)
            start = page.get("LastEvaluatedKey")
            if not start:
                return

    # -- 쓰기
    def new_item(self, pk: str, sk: str, entity_type: str, data: dict, *, owner: str | None = None,
                 gsi: tuple[str, str] | None = None, expires_at: int | None = None) -> dict:
        """처음 쓰는 아이템 전체. 모델이 `createdAt`을 가지고 있으면 그 값을 쓴다."""
        now = self.stamp()
        item = {"PK": pk, "SK": sk, "entityType": entity_type, "schemaVersion": SCHEMA_VERSION,
                "createdAt": now, "updatedAt": now}
        if owner:
            item["ownerUserId"] = owner
        if gsi:
            item["GSI1PK"], item["GSI1SK"] = gsi
        if expires_at is not None:
            item["expiresAt"] = expires_at
        item.update(data)
        item["updatedAt"] = now
        return to_ddb(item)

    def put_if_new(self, item: dict, *, condition: str = NOT_EXISTS, values: dict | None = None) -> bool:
        """조건부 put. 조건이 어긋나면(이미 있으면) False."""
        params: dict[str, Any] = {"Item": item, "ConditionExpression": condition}
        if values:
            params["ExpressionAttributeValues"] = to_ddb(values)
        try:
            with aws_errors(self.service, conditional=True):
                self.table.put_item(**params)
        except ConditionFailed:
            return False
        return True

    def upsert(self, pk: str, sk: str, entity_type: str, model, *, owner: str | None = None,
               gsi: tuple[str, str] | None = None, drop_gsi: bool = False, expires_at: int | None = None,
               keep: Sequence[str] = ()) -> None:
        """모델 전체를 아이템에 쓴다 (UpdateItem). 없던 아이템이면 만들고, 있으면 `createdAt`은 그대로 둔다.

        모델에서 None이라 빠진 칸은 아이템에서도 지운다. `keep`에 적은 칸은 지우지 않는다 (한 번만 쓰는 값).
        gsi가 있으면 GSI1 키를 쓰고, drop_gsi면 GSI1 키를 지운다.
        """
        data = model.to_api()
        sets: dict[str, Any] = {k: v for k, v in data.items()}
        sets.update({"entityType": entity_type, "schemaVersion": SCHEMA_VERSION, "updatedAt": self.stamp()})
        if owner:
            sets["ownerUserId"] = owner
        if gsi:
            sets["GSI1PK"], sets["GSI1SK"] = gsi
        if expires_at is not None:
            sets["expiresAt"] = expires_at
        removes = sorted(_aliases(type(model)) - set(data) - set(keep))
        if drop_gsi:
            removes += ["GSI1PK", "GSI1SK"]
        names: dict[str, str] = {}
        values: dict[str, Any] = {}
        parts: list[str] = []
        for i, (key, value) in enumerate(sets.items()):
            names[f"#s{i}"] = key
            values[f":s{i}"] = to_ddb(value)
            parts.append(f"#s{i} = :s{i}")
        if "createdAt" not in sets:
            names["#ca"] = "createdAt"
            values[":ca"] = sets["updatedAt"]
            parts.append("#ca = if_not_exists(#ca, :ca)")
        expression = "SET " + ", ".join(parts)
        if removes:
            rem = []
            for i, key in enumerate(removes):
                names[f"#r{i}"] = key
                rem.append(f"#r{i}")
            expression += " REMOVE " + ", ".join(rem)
        with aws_errors(self.service):
            self.table.update_item(Key={"PK": pk, "SK": sk}, UpdateExpression=expression,
                                   ExpressionAttributeNames=names, ExpressionAttributeValues=values)

    def delete(self, pk: str, sk: str) -> None:
        with aws_errors(self.service):
            self.table.delete_item(Key={"PK": pk, "SK": sk})


def _default_resource(region: str | None = None):
    return boto3.resource("dynamodb", region_name=region) if region else boto3.resource("dynamodb")


# ---------------------------------------------------------------- catalog
class DynamoCatalog:
    """`team07-catalog`. 테이블 이름은 인자, 없으면 환경변수 `TABLE_CATALOG`."""

    META_PK, META_SK = "META#OPP", "INGEST"

    def __init__(self, resource=None, table_name: str | None = None, *,
                 now: Callable[[], datetime] = clock.now_kst, sleep: Callable[[float], None] = time.sleep,
                 max_retries: int = 5):
        self.resource = resource or _default_resource()
        self.t = _Table(self.resource, table_name or require_env("TABLE_CATALOG"), service="dynamodb", now=now)
        self.sleep = sleep
        self.max_retries = max_retries

    # -- 키
    @staticmethod
    def _posting_pk(job_posting_id: str) -> str:
        return f"POSTING#{job_posting_id}"

    # -- 읽기
    def get_latest(self, job_posting_id):
        item = self.t.get(self._posting_pk(job_posting_id), "LATEST")
        return PostingLatest.model_validate(item) if item else None

    def batch_get_latest(self, job_posting_ids):
        ids = list(dict.fromkeys(job_posting_ids))
        found: dict[str, PostingLatest] = {}
        for start in range(0, len(ids), BATCH_GET_LIMIT):
            keys = [{"PK": self._posting_pk(i), "SK": "LATEST"} for i in ids[start:start + BATCH_GET_LIMIT]]
            for item in self._batch_get(keys):
                latest = PostingLatest.model_validate(item)
                found[latest.job_posting_id] = latest
        return found

    def _batch_get(self, keys: list[dict]) -> list[dict]:
        """BatchGetItem. 처리 못 한 키(UnprocessedKeys)는 짧게 쉬며 다시 읽는다."""
        items: list[dict] = []
        request = {self.t.name: {"Keys": keys}}
        for attempt in range(self.max_retries + 1):
            with aws_errors("dynamodb"):
                response = self.resource.batch_get_item(RequestItems=request)
            items += [from_ddb(i) for i in response.get("Responses", {}).get(self.t.name, [])]
            request = response.get("UnprocessedKeys") or {}
            if not request:
                return items
            self.sleep(min(0.05 * 2 ** attempt, 1.0))
        raise aws_service_error("dynamodb")

    def get_snapshot(self, job_posting_id, snapshot_id):
        item = self.t.get(self._posting_pk(job_posting_id), f"SNAP#{snapshot_id}")
        return PostingSnapshot.model_validate(item) if item else None

    def get_alts(self, job_posting_id):
        item = self.t.get(self._posting_pk(job_posting_id), "ALTS")
        return AltCandidates.model_validate(item) if item else None

    def query_postings_by_sido(self, sido, *, closes_from, limit=100):
        """GSI1 `POSTING#{sido}`을 마감일이 빠른 순으로 읽는다. 마감일이 같으면 ID순이라, 한도 끝의 동률까지 읽어 자른다."""
        rows: list[PostingLatest] = []
        for item in self.t.query(IndexName=GSI1, ScanIndexForward=True, Limit=limit + 1,
                                 KeyConditionExpression="GSI1PK = :pk AND GSI1SK >= :from",
                                 ExpressionAttributeValues={":pk": f"POSTING#{sido}", ":from": closes_from}):
            row = PostingLatest.model_validate(item)
            if len(rows) >= limit and row.closes_at != rows[limit - 1].closes_at:
                break
            rows.append(row)
        return sorted(rows, key=lambda p: (p.closes_at, p.job_posting_id))[:limit]

    def query_policies(self, region_key):
        rows = [Policy.model_validate(i) for i in self.t.query(
            IndexName=GSI1, KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": f"POLICY#{region_key}"})]
        return sorted(rows, key=lambda p: (p.apply_end, p.policy_id))

    def get_policy(self, policy_id):
        item = self.t.get(f"POLICY#{policy_id}", "META")
        return Policy.model_validate(item) if item else None

    def get_company(self, company_id):
        item = self.t.get(f"COMPANY#{company_id}", "META")
        return CompanyRecord.model_validate(item) if item else None

    def list_companies(self, sido):
        rows = [CompanyRecord.model_validate(i) for i in self.t.query(
            IndexName=GSI1, KeyConditionExpression="GSI1PK = :pk",
            ExpressionAttributeValues={":pk": f"COMPANY#{sido}"})]
        return sorted(rows, key=lambda c: c.name)

    def data_as_of(self):
        item = self.t.get(self.META_PK, self.META_SK)
        return item.get("dataAsOf") if item else None

    # -- 쓰기 (수집·보강 배치만)
    def put_snapshot(self, snapshot):
        self.t.upsert(self._posting_pk(snapshot.job_posting_id), f"SNAP#{snapshot.snapshot_id}",
                      "PostingSnapshot", snapshot)

    def put_latest(self, latest):
        """근무지를 모르거나 시·도가 없으면 GSI 값을 넣지 않는다. 그러면 시·도별 조회에서 빠진다."""
        sido = None if latest.work_region.unknown else latest.work_region.sido
        self.t.upsert(self._posting_pk(latest.job_posting_id), "LATEST", "PostingLatest", latest,
                      gsi=(f"POSTING#{sido}", latest.closes_at) if sido else None, drop_gsi=not sido)

    def put_alts(self, alts):
        self.t.upsert(self._posting_pk(alts.job_posting_id), "ALTS", "AltCandidates", alts)

    def put_policy(self, policy):
        self.t.upsert(f"POLICY#{policy.policy_id}", "META", "Policy", policy,
                      gsi=(f"POLICY#{policy.region_key()}", policy.apply_end))

    def put_company(self, company):
        self.t.upsert(f"COMPANY#{company.company_id}", "META", "Company", company,
                      gsi=(f"COMPANY#{company.sido}", company.name) if company.sido else None,
                      drop_gsi=not company.sido)

    def set_data_as_of(self, iso):
        now = self.t.stamp()
        with aws_errors("dynamodb"):
            self.t.table.update_item(
                Key={"PK": self.META_PK, "SK": self.META_SK},
                UpdateExpression="SET dataAsOf = :d, entityType = :e, schemaVersion = :v, updatedAt = :u, "
                                 "createdAt = if_not_exists(createdAt, :u)",
                ExpressionAttributeValues={":d": iso, ":e": "IngestMeta", ":v": SCHEMA_VERSION, ":u": now})


# ---------------------------------------------------------------- career-mentor
_WEEK_RE = re.compile(r"^(\d{4})-W(\d{2})$")


def _week_start(week_key: str) -> date:
    match = _WEEK_RE.match(week_key)
    if not match:
        raise invalid_input("주 키 형식이 올바르지 않아요.")
    try:
        return date.fromisocalendar(int(match[1]), int(match[2]), 1)
    except ValueError:
        raise invalid_input("주 키 형식이 올바르지 않아요.") from None


class DynamoUsers:
    """`team07-career-mentor`의 `USER#{userId}` 아래 B 데이터. 테이블 이름은 인자, 없으면 환경변수 `TABLE_CAREER_MENTOR`.

    `retention_days`는 알림함 보관 일수(설정 `notifications.retentionDays`)다.
    """

    def __init__(self, resource=None, table_name: str | None = None, *, retention_days: int,
                 idem_ttl_hours: int = IDEM_TTL_HOURS, now: Callable[[], datetime] = clock.now_kst):
        self.resource = resource or _default_resource()
        self.t = _Table(self.resource, table_name or require_env("TABLE_CAREER_MENTOR"), service="dynamodb", now=now)
        self.retention_days = retention_days
        self.idem_ttl_hours = idem_ttl_hours

    @staticmethod
    def _pk(user_id: str) -> str:
        return f"USER#{user_id}"

    def _now_epoch(self) -> int:
        return _epoch(self.t.now())

    # -- 프로필·설정
    def get_basic_profile(self, user_id):
        item = self.t.get(self._pk(user_id), "PROFILE#BASIC")
        return BasicProfile.model_validate(item) if item else None

    def get_prefs(self, user_id):
        item = self.t.get(self._pk(user_id), "OPP#PREFS")
        return OppPrefs.model_validate(item) if item else OppPrefs()

    def put_prefs(self, user_id, prefs):
        """설정을 쓴다. 이유 질문을 이미 내려 줬다는 표시(`leaveReasonAskedAt`)는 값이 없는 요청으로 지우지 않는다 (T-09)."""
        self.t.upsert(self._pk(user_id), "OPP#PREFS", "OppPrefs", prefs, owner=user_id, keep=["leaveReasonAskedAt"])

    def mark_leave_reason_asked(self, user_id, asked_at):
        now = self.t.stamp()
        try:
            with aws_errors("dynamodb", conditional=True):
                self.t.table.update_item(
                    Key={"PK": self._pk(user_id), "SK": "OPP#PREFS"},
                    UpdateExpression="SET leaveReasonAskedAt = :a, entityType = :e, schemaVersion = :v, "
                                     "ownerUserId = :o, updatedAt = :u, createdAt = if_not_exists(createdAt, :u)",
                    ConditionExpression="attribute_not_exists(leaveReasonAskedAt)",
                    ExpressionAttributeValues={":a": asked_at, ":e": "OppPrefs", ":v": SCHEMA_VERSION,
                                               ":o": user_id, ":u": now})
        except ConditionFailed:
            return False
        return True

    # -- 저장·목표 공고
    def _saved_item(self, user_id: str, item: SavedItem) -> dict:
        # 비부산 공고만 GSI1에 WATCH#{jobMajor}를 둔다 (P1 B-12)
        watch = (f"WATCH#{item.job_major}", f"USER#{user_id}") if not item.is_busan and item.job_major else None
        return self.t.new_item(self._pk(user_id), f"OPP#SAVED#{item.job_posting_id}", "SavedItem", item.to_api(),
                               owner=user_id, gsi=watch)

    def get_saved(self, user_id, job_posting_id):
        item = self.t.get(self._pk(user_id), f"OPP#SAVED#{job_posting_id}")
        return SavedItem.model_validate(item) if item else None

    def list_saved(self, user_id):
        rows = [SavedItem.model_validate(i) for i in self._list(user_id, "OPP#SAVED#")]
        return sorted(rows, key=lambda s: s.job_posting_id)

    def _list(self, user_id: str, prefix: str, **kwargs) -> Iterator[dict]:
        return self.t.query(KeyConditionExpression="PK = :pk AND begins_with(SK, :p)",
                            ExpressionAttributeValues={":pk": self._pk(user_id), ":p": prefix}, **kwargs)

    def put_saved(self, user_id, item, workspace_tx=None):
        """`OPP#SAVED#`를 조건부로 쓴다. workspace_tx가 있으면 한 트랜잭션으로 같이 쓴다. 이미 있으면 False."""
        row = self._saved_item(user_id, item)
        if workspace_tx is None:
            return self.t.put_if_new(row)
        put = {"Put": {"TableName": self.t.name, "Item": row, "ConditionExpression": NOT_EXISTS}}
        try:
            # workspace_tx는 `backend/workspace.py`의 resource 형식 dict라서 resource의 client로 보낸다
            with aws_errors("dynamodb", conditional=True):
                self.resource.meta.client.transact_write_items(TransactItems=[put, workspace_tx])
        except ConditionFailed:
            return False
        return True

    def update_saved(self, user_id, item):
        watch = (f"WATCH#{item.job_major}", f"USER#{user_id}") if not item.is_busan and item.job_major else None
        self.t.upsert(self._pk(user_id), f"OPP#SAVED#{item.job_posting_id}", "SavedItem", item, owner=user_id,
                      gsi=watch, drop_gsi=watch is None)

    # -- 정책 알림 신청
    def get_alert(self, user_id, policy_id):
        item = self.t.get(self._pk(user_id), f"OPP#ALERT#{policy_id}")
        return PolicyAlert.model_validate(item) if item else None

    def list_alerts(self, user_id):
        rows = [PolicyAlert.model_validate(i) for i in self._list(user_id, "OPP#ALERT#")]
        return sorted(rows, key=lambda a: a.policy_id)

    def put_alert(self, user_id, alert):
        item = self.t.new_item(self._pk(user_id), f"OPP#ALERT#{alert.policy_id}", "PolicyAlert", alert.to_api(),
                               owner=user_id)
        return self.t.put_if_new(item)

    def update_alert(self, user_id, alert):
        self.t.upsert(self._pk(user_id), f"OPP#ALERT#{alert.policy_id}", "PolicyAlert", alert, owner=user_id)

    def delete_alert(self, user_id, policy_id):
        self.t.delete(self._pk(user_id), f"OPP#ALERT#{policy_id}")

    # -- 알림함
    def put_notification(self, user_id, notification):
        expires = _epoch(clock.parse_as_of(notification.created_at) + timedelta(days=self.retention_days))
        item = self.t.new_item(self._pk(user_id), f"OPP#NOTI#{notification.notification_id}", "Notification",
                               notification.to_api(), owner=user_id, expires_at=expires)
        return self.t.put_if_new(item)

    def list_notifications(self, user_id, *, cursor=None, limit=20):
        """최신순. 한 개 더 읽어 다음 쪽이 있는지 알고, cursor는 이번 쪽 마지막 notificationId다.

        TTL 삭제는 늦을 수 있어서 보관 기간이 지난 아이템은 건너뛴다.
        """
        kwargs: dict[str, Any] = {"ScanIndexForward": False}
        if cursor:
            kwargs["ExclusiveStartKey"] = {"PK": self._pk(user_id), "SK": f"OPP#NOTI#{cursor}"}
        now = self._now_epoch()
        rows: list[Notification] = []
        for item in self._list(user_id, "OPP#NOTI#", **kwargs):
            if item.get("expiresAt", now + 1) <= now:
                continue
            rows.append(Notification.model_validate(item))
            if len(rows) > limit:
                break
        page = rows[:limit]
        return page, (page[-1].notification_id if len(rows) > limit else None)

    def mark_notification_read(self, user_id, notification_id):
        try:
            with aws_errors("dynamodb", conditional=True):
                self.t.table.update_item(
                    Key={"PK": self._pk(user_id), "SK": f"OPP#NOTI#{notification_id}"},
                    UpdateExpression="SET #r = :t, updatedAt = :u", ConditionExpression="attribute_exists(SK)",
                    ExpressionAttributeNames={"#r": "read"},
                    ExpressionAttributeValues={":t": True, ":u": self.t.stamp()})
        except ConditionFailed:
            return False
        return True

    # -- 즉시 알림 횟수
    def incr_immediate_count(self, user_id, week_key, limit):
        """한도 안이면 1 올리고 True. 조건부 ADD라서 동시에 불러도 한도를 넘지 않는다 (T-11)."""
        if limit <= 0:
            return False
        expires = _epoch(clock.at_hour(_week_start(week_key) + timedelta(weeks=CAP_TTL_WEEKS), 0))
        now = self.t.stamp()
        try:
            with aws_errors("dynamodb", conditional=True):
                self.t.table.update_item(
                    Key={"PK": self._pk(user_id), "SK": f"OPP#CAP#{week_key}"},
                    UpdateExpression="SET entityType = :e, schemaVersion = :v, ownerUserId = :o, updatedAt = :u, "
                                     "createdAt = if_not_exists(createdAt, :u), expiresAt = :x ADD immediateCount :one",
                    ConditionExpression="attribute_not_exists(immediateCount) OR immediateCount < :limit",
                    ExpressionAttributeValues={":e": "ImmediateCap", ":v": SCHEMA_VERSION, ":o": user_id, ":u": now,
                                               ":x": expires, ":one": 1, ":limit": limit})
        except ConditionFailed:
            return False
        return True

    # -- 설명 문장 캐시
    def get_explanation(self, user_id, job_posting_id):
        item = self.t.get(self._pk(user_id), f"OPP#EXPL#{job_posting_id}")
        if not item or item.get("expiresAt", self._now_epoch() + 1) <= self._now_epoch():
            return None  # TTL 삭제가 늦어도 만료된 캐시는 쓰지 않는다
        return ExplanationCache.model_validate(item)

    def put_explanation(self, user_id, cache, ttl_hours):
        expires = _epoch(clock.parse_as_of(cache.created_at) + timedelta(hours=ttl_hours))
        self.t.upsert(self._pk(user_id), f"OPP#EXPL#{cache.job_posting_id}", "ExplanationCache", cache,
                      owner=user_id, expires_at=expires)

    # -- 멱등 (D-31)
    def idem_begin(self, user_id, key, request_hash):
        """처음이면 NEW, 같은 본문 재요청이면 REPLAY(저장된 result), 같은 키에 다른 본문이면 CONFLICT."""
        pk, sk = self._pk(user_id), f"IDEM#{key}"
        now = self._now_epoch()
        expires = _epoch(self.t.now() + timedelta(hours=self.idem_ttl_hours))
        for _ in range(2):
            item = self.t.new_item(pk, sk, "Idempotency", {"requestHash": request_hash}, owner=user_id,
                                   expires_at=expires)
            # 이미 있어도 보관 시간이 지난(TTL 삭제 전) 아이템은 덮어쓴다
            if self.t.put_if_new(item, condition="attribute_not_exists(SK) OR expiresAt <= :now",
                                 values={":now": now}):
                return IdemResult("NEW")
            row = self.t.get(pk, sk, consistent=True)
            if row is None:  # 조건이 어긋난 사이에 지워졌다. 한 번 더 시도한다
                continue
            if row.get("requestHash") != request_hash:
                return IdemResult("CONFLICT")
            return IdemResult("REPLAY", row.get("result"))
        raise aws_service_error("dynamodb")

    def idem_finish(self, user_id, key, result):
        """처리 결과를 남긴다. 키가 없으면(보관 시간이 지났다) 새로 만들지 않고 넘어간다."""
        try:
            with aws_errors("dynamodb", conditional=True):
                self.t.table.update_item(
                    Key={"PK": self._pk(user_id), "SK": f"IDEM#{key}"},
                    UpdateExpression="SET #res = :r, updatedAt = :u", ConditionExpression="attribute_exists(SK)",
                    ExpressionAttributeNames={"#res": "result"},
                    ExpressionAttributeValues={":r": to_ddb(result), ":u": self.t.stamp()})
        except ConditionFailed:
            return
