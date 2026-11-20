"""워크스페이스 — 공고 하나에 대한 분석·첨삭·학습 경로·면접을 묶는 곳 (DB 스키마 §2.1, §2.3).

다른 파트가 코드에서 바로 부르는 함수:
  ensure_workspace(user_id, job_posting_id=..., snapshot_id=...)  → (item, created)
  workspace_put(user_id, ...)       → TransactWriteItems에 넣을 Put (B: OPP#SAVED#와 한 트랜잭션)
  set_status(user_id, ws_id, status)

규칙
  - workspaceId = ws-{jobPostingId} (공고 없이 NCS 직무로 만들면 ws-ncs-{ncsCode})
  - 같은 공고는 두 번 만들어지지 않는다 (attribute_not_exists 조건) → 기존 것을 돌려줌
  - 지원 상태는 여기 한 곳에만 둔다 (B의 OPP#SAVED#에는 두지 않음)
"""

import os
import re

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from common import TeamError, now_iso, to_dynamo, to_plain

TABLE = os.environ.get("TABLE_CAREER_MENTOR", "team07-career-mentor")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
STATUSES = ("INTEREST", "PLANNED", "PREPARING", "APPLIED", "RESULT", "CLOSED")  # B의 저장 상태 + CLOSED
DOC_TYPES = ("RESUME", "COVER_LETTER")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")  # '#' 금지 (키 구분자, 주소에서 깨짐)
LINKED_TYPES = ("ANALYSIS", "REVIEW", "PATH", "INTERVIEW")

_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    return _table


def check_id(value, name):
    if not isinstance(value, str) or not ID_RE.match(value):
        raise TeamError(400, "INVALID_INPUT", f"{name} 형식이 올바르지 않아요.")
    return value


def workspace_id(job_posting_id=None, ncs_code=None):
    if job_posting_id:
        return f"ws-{check_id(job_posting_id, 'jobPostingId')}"
    if ncs_code:
        return f"ws-ncs-{check_id(ncs_code, 'targetNcsCode')}"
    raise TeamError(400, "INVALID_INPUT", "jobPostingId 또는 targetNcsCode가 필요해요.")


def key(user_id, ws_id):
    return {"PK": f"USER#{user_id}", "SK": f"WORKSPACE#{ws_id}"}


def list_key(user_id, status, updated_at):
    return {"GSI1PK": f"USER#{user_id}#WSLIST", "GSI1SK": f"{status}#{updated_at}"}


def new_item(user_id, job_posting_id=None, snapshot_id=None, ncs_code=None, status="INTEREST"):
    if status not in STATUSES:
        raise TeamError(400, "INVALID_INPUT", "지원 상태 값이 올바르지 않아요.")
    ws_id, now = workspace_id(job_posting_id, ncs_code), now_iso()
    return {**key(user_id, ws_id), **list_key(user_id, status, now), "entityType": "Workspace", "schemaVersion": "1.0",
            "ownerUserId": user_id, "workspaceId": ws_id, "jobPostingId": job_posting_id, "snapshotId": snapshot_id,
            "targetNcsCode": ncs_code, "status": status, "selectedDocuments": {}, "latestAnalysisId": None,
            "latestReviewId": None, "latestLearningPathId": None, "latestInterviewId": None, "createdAt": now, "updatedAt": now}


def workspace_put(user_id, **kwargs):
    """B의 POST /saved: OPP#SAVED#와 함께 TransactWriteItems에 넣는다 (client 형식이 아니라 resource 형식 dict)."""
    return {"Put": {"TableName": TABLE, "Item": to_dynamo(new_item(user_id, **kwargs)),
                    "ConditionExpression": "attribute_not_exists(SK)"}}


def get_workspace(user_id, ws_id):
    item = table().get_item(Key=key(user_id, check_id(ws_id, "workspaceId"))).get("Item")
    if not item:
        raise TeamError(404, "WORKSPACE_NOT_FOUND", "워크스페이스를 찾을 수 없어요.")
    return to_plain(item)


def ensure_workspace(user_id, job_posting_id=None, snapshot_id=None, ncs_code=None, status="INTEREST"):
    """없으면 만들고, 있으면 기존 것을 돌려준다. → (item, created)"""
    item = new_item(user_id, job_posting_id, snapshot_id, ncs_code, status)
    try:
        table().put_item(Item=to_dynamo(item), ConditionExpression="attribute_not_exists(SK)")
        return item, True
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return get_workspace(user_id, item["workspaceId"]), False


def update_workspace(user_id, ws_id, status=None, selected_documents=None):
    """지원 상태·사용할 문서 버전 변경. 상태가 바뀌면 목록 정렬 키(GSI1SK)도 같이 바꾼다."""
    current = get_workspace(user_id, ws_id)
    now = now_iso()
    values = {"updatedAt": now}
    if status is not None:
        if status not in STATUSES:
            raise TeamError(400, "INVALID_INPUT", "지원 상태 값이 올바르지 않아요.")
        values["status"] = status
    if selected_documents is not None:
        if not isinstance(selected_documents, dict) or not set(selected_documents) <= set(DOC_TYPES):
            raise TeamError(400, "INVALID_INPUT", "selectedDocuments는 RESUME, COVER_LETTER만 받아요.")
        for doc_type, ref in selected_documents.items():
            if ref is None:
                continue
            if not isinstance(ref, dict) or not isinstance(ref.get("version"), int) or ref["version"] < 1:
                raise TeamError(400, "INVALID_INPUT", "문서는 {documentId, version}으로 보내 주세요.")
            check_id(ref.get("documentId"), "documentId")
        values["selectedDocuments"] = {**(current.get("selectedDocuments") or {}), **selected_documents}
    values["GSI1SK"] = f"{values.get('status', current['status'])}#{now}"

    names = {f"#k{i}": k for i, k in enumerate(values)}
    vals = {f":v{i}": to_dynamo(v) for i, v in enumerate(values.values())}
    table().update_item(Key=key(user_id, ws_id), UpdateExpression="SET " + ", ".join(f"#k{i} = :v{i}" for i in range(len(values))),
                        ExpressionAttributeNames=names, ExpressionAttributeValues=vals, ConditionExpression="attribute_exists(SK)")
    return {**current, **values}


def set_status(user_id, ws_id, status):
    return update_workspace(user_id, ws_id, status=status)


def list_workspaces(user_id, status=None, limit=50):
    cond = Key("GSI1PK").eq(f"USER#{user_id}#WSLIST")
    if status:
        if status not in STATUSES:
            raise TeamError(400, "INVALID_INPUT", "지원 상태 값이 올바르지 않아요.")
        cond &= Key("GSI1SK").begins_with(f"{status}#")
    items = table().query(IndexName="GSI1", KeyConditionExpression=cond, ScanIndexForward=False, Limit=limit)["Items"]
    # GSI로 읽어도 소유자를 다시 확인 (DB 스키마 원칙 4)
    items = [to_plain(i) for i in items if i.get("ownerUserId") == user_id]
    return sorted(items, key=lambda i: i["updatedAt"], reverse=True)


def linked_items(user_id, ws_id):
    """워크스페이스에 연결된 분석·첨삭·학습 경로·면접 (최신순, 종류별)."""
    get_workspace(user_id, ws_id)  # 없으면 404
    items = table().query(IndexName="GSI1", KeyConditionExpression=Key("GSI1PK").eq(f"USER#{user_id}#WS#{ws_id}"),
                          ScanIndexForward=False)["Items"]
    grouped = {t: [] for t in LINKED_TYPES}
    for raw in items:
        item = to_plain(raw)
        if item.get("ownerUserId") != user_id:
            continue
        kind = item["GSI1SK"].split("#", 1)[0]
        if kind in grouped:
            grouped[kind].append({"id": item["SK"].split("#", 1)[1], "createdAt": item.get("createdAt"),
                                  "status": item.get("status"), "entityType": item.get("entityType")})
    return grouped
