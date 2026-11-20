"""팀 공통 규칙: 사용자 식별, 오류 형식, DynamoDB 값 변환."""

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

KST = timezone(timedelta(hours=9))
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")


def now_iso():
    return datetime.now(KST).isoformat(timespec="seconds")


def new_request_id():
    return f"req-{uuid.uuid4().hex[:12]}"


class TeamError(Exception):
    """팀 공통 오류. 응답: {error: {code, message, requestId, retryable}}"""

    def __init__(self, status, code, message, retryable=False):
        super().__init__(message)
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def json_response(status, body, request_id=None):
    headers = {"Content-Type": "application/json; charset=utf-8", "Access-Control-Allow-Origin": ALLOWED_ORIGIN}
    if request_id:
        headers["X-Request-Id"] = request_id
    return {"statusCode": status, "headers": headers, "body": json.dumps(to_plain(body), ensure_ascii=False)}


def error_response(err: TeamError, request_id):
    return json_response(
        err.status,
        {"error": {"code": err.code, "message": err.message, "requestId": request_id, "retryable": err.retryable}},
        request_id,
    )


def header(event, name):
    return (event.get("headers") or {}).get(name.lower())


def get_claims(event):
    return ((event.get("requestContext", {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}


def get_user_id(event):
    """userId는 인증 정보에서만 읽는다. 요청 본문의 userId는 절대 쓰지 않는다.

    배포 환경: API Gateway JWT authorizer가 검증한 Cognito 토큰의 sub
    로컬 테스트: ALLOW_DEV_USER_HEADER=1 일 때만 X-User-Id 헤더 허용 (배포 Lambda에서는 꺼져 있음)
    """
    user_id = get_claims(event).get("sub")
    if not user_id and os.environ.get("ALLOW_DEV_USER_HEADER") == "1":
        user_id = header(event, "x-user-id")
    if not user_id:
        raise TeamError(401, "UNAUTHORIZED", "사용자 정보가 없어요. 다시 접속해 주세요.")
    if len(user_id) > 128 or "#" in user_id:
        raise TeamError(400, "INVALID_INPUT", "사용자 정보 형식이 올바르지 않아요.")
    return user_id


def hash_user_id(user_id: str) -> str:
    """인증된 Cognito sub로 개인 문서 저장·삭제에 동일한 S3 접두사를 만든다."""
    return sha256(user_id.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- DynamoDB 값 변환
# DynamoDB는 float를 못 받고, 읽으면 Decimal로 돌려준다.


def to_dynamo(value):
    return json.loads(json.dumps(value, ensure_ascii=False), parse_float=Decimal)


def to_plain(value):
    if isinstance(value, list):
        return [to_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: to_plain(v) for k, v in value.items()}
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value
