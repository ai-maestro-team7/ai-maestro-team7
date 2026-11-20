"""공통 사용자 API — /api/v1/me/* (토큰 필요)

  GET   /api/v1/me/profile                       기본 프로필 (PROFILE#BASIC)
  PUT   /api/v1/me/profile                       기본 프로필 부분 수정 (보낸 필드만)
  GET   /api/v1/me/workspaces?status=PREPARING   내 워크스페이스 목록 (최근순)
  POST  /api/v1/me/workspaces                    {jobPostingId, snapshotId} 또는 {targetNcsCode} → 없으면 만들고 있으면 기존 것
  GET   /api/v1/me/workspaces/{wsId}             워크스페이스 하나 (+ 연결된 분석·첨삭·학습 경로·면접)
  PATCH /api/v1/me/workspaces/{wsId}             {status, selectedDocuments}

역량 프로필(이력서에서 뽑은 역량)은 A의 /api/v1/mentoring/profiles/me — 여기와 다르다.
"""

import base64
import json
import os
import re

import boto3

import workspace as ws
from common import TeamError, error_response, get_user_id, json_response, new_request_id, now_iso, to_dynamo, to_plain

TABLE = os.environ.get("TABLE_CAREER_MENTOR", "team07-career-mentor")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_table = None


def table():
    global _table
    if _table is None:
        _table = boto3.resource("dynamodb", region_name=REGION).Table(TABLE)
    return _table


def parse_json(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.")
    if not isinstance(data, dict):
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.")
    return data


# ---------------------------------------------------------------- 기본 프로필 필드 검사 (DB 스키마 §2.1, B 명세 §10.3)

SIDO = re.compile(r"^\d{2}$")
SIGUNGU = re.compile(r"^\d{5}$")
YEAR_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def enum(*values):
    return lambda v: v in values


def text(max_len):
    return lambda v: isinstance(v, str) and 0 < len(v.strip()) <= max_len


def int_range(lo, hi):
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def desired_jobs(v):
    if not isinstance(v, list) or len(v) > 3:
        return False
    for job in v:
        if not isinstance(job, dict) or not set(job) <= {"work24Code", "ncsCode", "name"} or not text(50)(job.get("name")):
            return False
        for code in ("work24Code", "ncsCode"):
            if job.get(code) is not None and not (isinstance(job[code], str) and re.match(r"^[0-9A-Za-z_]{1,20}$", job[code])):
                return False
    return True


PROFILE_FIELDS = {
    "birthYear": int_range(1950, 2015),
    "residenceSido": lambda v: isinstance(v, str) and bool(SIDO.match(v)),
    "residenceSigungu": lambda v: isinstance(v, str) and bool(SIGUNGU.match(v)),
    "residenceSince": lambda v: isinstance(v, str) and bool(YEAR_MONTH.match(v)),
    "universityRegion": lambda v: isinstance(v, str) and bool(SIDO.match(v)),
    "graduationStatus": enum("ENROLLED", "GRADUATING", "GRADUATED"),
    "educationLevel": enum("HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "DOCTOR"),
    "major": text(50),
    "careerYears": int_range(0, 50),
    "employmentStatus": enum("UNEMPLOYED", "EMPLOYED", "PART_TIME", "STUDENT"),
    "monthlyIncome": int_range(0, 100_000_000),
    "householdIncomeLevel": enum("under_100", "under_150", "over_150", "unknown"),
    "desiredJobs": desired_jobs,
    "desiredRegion": lambda v: v == "ALL" or (isinstance(v, str) and bool(SIDO.match(v))),
    "priorities": lambda v: isinstance(v, list) and len(v) <= 3 and all(
        p in ("SALARY", "GROWTH", "STABILITY", "WORK_LIFE", "HOUSING", "LOCATION") for p in v),
    "talentPoolConsent": lambda v: isinstance(v, bool),
    # 채팅 조건 저장 (D-40). 사용자가 화면 버튼을 눌렀을 때만 들어온다
    "desiredSalaryMin": int_range(0, 100_000),  # 만 원/년
    "desiredCareerType": enum("NEW", "EXPERIENCED", "ANY"),
}
SYSTEM_FIELDS = {"PK", "SK", "entityType", "schemaVersion", "ownerUserId", "createdAt", "updatedAt", "isDemo"}


def public_profile(item):
    return {k: v for k, v in to_plain(item).items() if k not in ("PK", "SK", "entityType", "schemaVersion", "ownerUserId")}


def h_get_profile(event, user_id, params):
    item = table().get_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE#BASIC"}).get("Item")
    if not item:
        raise TeamError(404, "PROFILE_NOT_FOUND", "아직 프로필이 없어요. 기본 정보를 입력해 주세요.")
    return 200, public_profile(item)


def h_put_profile(event, user_id, params):
    return 200, update_profile(user_id, parse_json(event))


def update_profile(user_id, data):
    """기본 프로필 부분 수정. PUT /me/profile과 채팅 Agent의 조건 저장 도구(D-40)가 같이 쓴다."""
    data = {k: v for k, v in data.items() if k not in ("userId", *SYSTEM_FIELDS)}  # 본문의 userId 등은 무시
    unknown = sorted(set(data) - set(PROFILE_FIELDS))
    if unknown:
        raise TeamError(400, "INVALID_INPUT", f"알 수 없는 항목이에요: {', '.join(unknown)}")
    bad = sorted(k for k, v in data.items() if v is not None and not PROFILE_FIELDS[k](v))
    if bad:
        raise TeamError(400, "INVALID_INPUT", f"값이 올바르지 않아요: {', '.join(bad)}")
    if not data:
        raise TeamError(400, "INVALID_INPUT", "바꿀 항목이 없어요.")

    now = now_iso()
    sets = ["#updatedAt = :now", "#createdAt = if_not_exists(#createdAt, :now)", "#et = :et", "#sv = :sv", "#owner = :owner"]
    removes = []
    names = {"#updatedAt": "updatedAt", "#createdAt": "createdAt", "#et": "entityType", "#sv": "schemaVersion", "#owner": "ownerUserId"}
    values = {":now": now, ":et": "BasicProfile", ":sv": "1.0", ":owner": user_id}
    for i, (k, v) in enumerate(data.items()):
        names[f"#f{i}"] = k
        if v is None:  # null을 보내면 그 항목을 지움
            removes.append(f"#f{i}")
        else:
            sets.append(f"#f{i} = :f{i}")
            values[f":f{i}"] = to_dynamo(v)
    expr = "SET " + ", ".join(sets) + (" REMOVE " + ", ".join(removes) if removes else "")
    item = table().update_item(Key={"PK": f"USER#{user_id}", "SK": "PROFILE#BASIC"}, UpdateExpression=expr,
                               ExpressionAttributeNames=names, ExpressionAttributeValues=values, ReturnValues="ALL_NEW")["Attributes"]
    return public_profile(item)


# ---------------------------------------------------------------- 워크스페이스


def public_ws(item):
    return {k: v for k, v in item.items() if k not in ("PK", "SK", "GSI1PK", "GSI1SK", "entityType", "schemaVersion", "ownerUserId")}


def h_list_ws(event, user_id, params):
    status = (event.get("queryStringParameters") or {}).get("status")
    return 200, {"items": [public_ws(i) for i in ws.list_workspaces(user_id, status)]}


def h_create_ws(event, user_id, params):
    data = parse_json(event)
    item, created = ws.ensure_workspace(user_id, job_posting_id=data.get("jobPostingId"),
                                        snapshot_id=data.get("snapshotId") and ws.check_id(data["snapshotId"], "snapshotId"),
                                        ncs_code=data.get("targetNcsCode"))
    return (201 if created else 200), {**public_ws(item), "created": created}


def h_get_ws(event, user_id, params):
    item = ws.get_workspace(user_id, params["wsId"])
    return 200, {**public_ws(item), "linked": ws.linked_items(user_id, params["wsId"])}


def h_patch_ws(event, user_id, params):
    data = parse_json(event)
    if not set(data) & {"status", "selectedDocuments"}:
        raise TeamError(400, "INVALID_INPUT", "status 또는 selectedDocuments를 보내 주세요.")
    item = ws.update_workspace(user_id, params["wsId"], status=data.get("status"), selected_documents=data.get("selectedDocuments"))
    return 200, public_ws(item)


ROUTES = [
    ("GET", r"/api/v1/me/profile", h_get_profile),
    ("PUT", r"/api/v1/me/profile", h_put_profile),
    ("GET", r"/api/v1/me/workspaces", h_list_ws),
    ("POST", r"/api/v1/me/workspaces", h_create_ws),
    ("GET", r"/api/v1/me/workspaces/(?P<wsId>[^/]+)", h_get_ws),
    ("PATCH", r"/api/v1/me/workspaces/(?P<wsId>[^/]+)", h_patch_ws),
]


def handle(event, method, path):
    request_id = new_request_id()
    try:
        matched = False
        for m, pattern, fn in ROUTES:
            match = re.fullmatch(pattern, path)
            if match:
                matched = True
                if m == method:
                    user_id = get_user_id(event)
                    status, body = fn(event, user_id, match.groupdict())
                    return json_response(status, body, request_id)
        if matched:
            raise TeamError(400, "INVALID_INPUT", f"{method} 메서드는 지원하지 않아요.")
        raise TeamError(404, "NOT_FOUND", "없는 주소예요.")
    except TeamError as e:
        return error_response(e, request_id)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {method} {path} {request_id}: {type(e).__name__}")
        return error_response(TeamError(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", True), request_id)
