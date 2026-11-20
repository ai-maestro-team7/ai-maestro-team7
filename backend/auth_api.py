"""로그인 — /api/v1/auth/* (토큰 없이 부르는 경로), /api/v1/me (토큰 필요)

아이디·비밀번호 로그인(로컬 로그인). 비밀번호 확인과 토큰 발급은 Cognito가 한다.
이 함수는 비밀번호를 저장하거나 로그에 남기지 않는다.

화면 흐름:
  1) POST /api/v1/auth/login {username, password} → {accessToken, refreshToken, expiresIn}
  2) 이후 모든 요청에 Authorization: Bearer {accessToken}
  3) 401이 오면 POST /api/v1/auth/refresh {refreshToken} → 새 accessToken
"""

import json
import os

import boto3
from botocore.exceptions import ClientError

from common import TeamError, error_response, get_claims, get_user_id, json_response, new_request_id

REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
CLIENT_ID = os.environ.get("COGNITO_CLIENT_ID", "")
_idp = None


def idp():
    global _idp
    if _idp is None:
        _idp = boto3.client("cognito-idp", region_name=REGION)
    return _idp


def body(event):
    import base64

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


def tokens(result):
    r = result["AuthenticationResult"]
    out = {"accessToken": r["AccessToken"], "idToken": r["IdToken"], "expiresIn": r["ExpiresIn"], "tokenType": "Bearer"}
    if r.get("RefreshToken"):
        out["refreshToken"] = r["RefreshToken"]
    return out


def auth(flow, params):
    if not CLIENT_ID:
        raise TeamError(503, "AWS_SERVICE_ERROR", "로그인 설정이 아직 없어요.", True)
    try:
        result = idp().initiate_auth(ClientId=CLIENT_ID, AuthFlow=flow, AuthParameters=params)
    except ClientError as e:
        code = e.response["Error"]["Code"]
        if code in ("NotAuthorizedException", "UserNotFoundException"):  # 어느 쪽이 틀렸는지 알려주지 않음
            raise TeamError(401, "INVALID_CREDENTIALS", "아이디 또는 비밀번호가 맞지 않아요.")
        if code == "TooManyRequestsException":
            raise TeamError(429, "RATE_LIMITED", "잠시 후 다시 시도해 주세요.", True)
        raise TeamError(503, "AWS_SERVICE_ERROR", "로그인을 처리하지 못했어요.", True)
    if result.get("ChallengeName"):  # 데모 계정은 영구 비밀번호라 여기 오지 않음
        raise TeamError(409, "PRECONDITION_NOT_MET", "비밀번호 변경이 필요한 계정이에요. 운영진에게 문의해 주세요.")
    return tokens(result)


def h_login(event):
    data = body(event)
    username, password = (data.get("username") or "").strip(), data.get("password") or ""
    if not username or not password or len(username) > 128 or len(password) > 256:
        raise TeamError(400, "INVALID_INPUT", "아이디와 비밀번호를 입력해 주세요.")
    return 200, auth("USER_PASSWORD_AUTH", {"USERNAME": username, "PASSWORD": password})


def h_refresh(event):
    token = body(event).get("refreshToken") or ""
    if not token:
        raise TeamError(400, "INVALID_INPUT", "refreshToken이 필요해요.")
    return 200, auth("REFRESH_TOKEN_AUTH", {"REFRESH_TOKEN": token})


def h_me(event):
    claims = get_claims(event)
    return 200, {"userId": get_user_id(event), "username": claims.get("username") or claims.get("cognito:username")}


ROUTES = {("POST", "/api/v1/auth/login"): h_login, ("POST", "/api/v1/auth/refresh"): h_refresh, ("GET", "/api/v1/me"): h_me}


def handle(event, method, path):
    request_id = new_request_id()
    fn = ROUTES.get((method, path))
    try:
        if not fn:
            raise TeamError(404, "NOT_FOUND", "없는 주소예요.")
        status, data = fn(event)
        return json_response(status, data, request_id)
    except TeamError as e:
        return error_response(e, request_id)
    except Exception as e:  # noqa: BLE001 — 비밀번호가 담긴 요청이라 내용은 로그에 남기지 않음
        print(f"[ERROR] {method} {path} {request_id}: {type(e).__name__}")
        return error_response(TeamError(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요.", True), request_id)
