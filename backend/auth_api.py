"""로그인 — /api/v1/auth/* (토큰 없이 부르는 경로), /api/v1/me (토큰 필요)

아이디·비밀번호 로그인(로컬 로그인). 비밀번호 확인과 토큰 발급은 Cognito가 한다.
이 함수는 비밀번호를 저장하거나 로그에 남기지 않는다.

화면 흐름:
  1) POST /api/v1/auth/login {username, password} → {accessToken, refreshToken, expiresIn}
  2) 이후 모든 요청에 Authorization: Bearer {accessToken}
  3) 401이 오면 POST /api/v1/auth/refresh {refreshToken} → 새 accessToken

소셜 로그인 (Google·카카오, Cognito 외부 로그인, OAuth 2.0 인가 코드 + PKCE. 이슈 #98):
  1) GET  /api/v1/auth/social/providers → {providers: [{id, label}]} (설정이 없으면 빈 목록)
  2) POST /api/v1/auth/social/start {provider, redirectUri, state, codeChallenge} → {authorizeUrl}
     화면이 authorizeUrl로 이동 → Cognito → 제공자 → {redirectUri}?code=…&state=…
  3) POST /api/v1/auth/social/token {code, redirectUri, codeVerifier} → 로그인 응답 + username
  제공자에게는 openid만 요청한다. 이름·이메일·전화번호를 받지 않고 저장하지 않는다.
  인가 코드, code_verifier, 토큰은 로그에 남기지 않는다.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

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


# ---------------------------------------------------------------- 소셜 로그인
# 화면에 보일 이름. 공개 id → (버튼 문구, 로그인 후 username). 여기 없는 id는 설정에 있어도 내보내지 않는다
SOCIAL_LABELS = {"google": ("Google", "Google 계정"), "kakao": ("카카오", "카카오 계정")}
SOCIAL_FALLBACK_NAME = "소셜 계정"
SOCIAL_TIMEOUT_SECONDS = 5
CALLBACK_PATH_SUFFIX = "/login/callback/"
PKCE_VALUE = re.compile(r"[A-Za-z0-9\-._~]{43,128}")  # RFC 7636 code_verifier·code_challenge
STATE_VALUE = re.compile(r"[A-Za-z0-9\-._~]{16,128}")
CODE_VALUE = re.compile(r"[A-Za-z0-9\-._~]{1,512}")
HOST_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")


def social_config():
    """(Cognito 도메인, 앱 클라이언트 ID, {공개 id: Cognito 제공자 이름}). 하나라도 없으면 None.

    환경 변수 (infra/setup-social-login.sh 가 넣는다):
      COGNITO_DOMAIN    호스트 이름만 (예: <접두사>.auth.<리전>.amazoncognito.com)
      SOCIAL_PROVIDERS  google=Google,kakao=Kakao (공개 id=Cognito 제공자 이름)
    """
    domain = os.environ.get("COGNITO_DOMAIN", "").strip()
    client_id = os.environ.get("COGNITO_CLIENT_ID", "").strip() or CLIENT_ID
    providers = {}
    for pair in os.environ.get("SOCIAL_PROVIDERS", "").split(","):
        pid, _, name = pair.partition("=")
        pid, name = pid.strip(), name.strip()
        if pid in SOCIAL_LABELS and name and pid not in providers:
            providers[pid] = name
    if not domain or not HOST_NAME.fullmatch(domain) or not client_id or not providers:
        return None
    return domain, client_id, providers


def require_social_config():
    config = social_config()
    if not config:
        raise TeamError(503, "AWS_SERVICE_ERROR", "소셜 로그인 설정이 아직 없어요.", True)
    return config


def text_field(data, key, pattern, message):
    value = data.get(key)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise TeamError(400, "INVALID_INPUT", message)
    return value


def redirect_uri_field(data):
    """https:// 주소(로컬 개발은 http://localhost만)이고 경로가 /login/callback/ 으로 끝나야 한다.

    Cognito도 앱 클라이언트에 등록한 주소와 글자 그대로 같은지 한 번 더 확인한다.
    """
    value = data.get("redirectUri")
    message = "redirectUri 형식이 올바르지 않아요."
    if not isinstance(value, str) or not 0 < len(value) <= 512 or any(c.isspace() or ord(c) < 32 for c in value):
        raise TeamError(400, "INVALID_INPUT", message)
    try:
        u = urllib.parse.urlsplit(value)
        port = u.port  # 숫자가 아닌 포트는 여기서 ValueError
    except ValueError:
        raise TeamError(400, "INVALID_INPUT", message)
    secure = u.scheme == "https" and u.hostname
    local = u.scheme == "http" and u.hostname == "localhost"
    if not (secure or local) or u.username or u.password or u.query or u.fragment or "#" in value \
            or not u.path.endswith(CALLBACK_PATH_SUFFIX) or port == 0:
        raise TeamError(400, "INVALID_INPUT", message)
    return value


def post_form(url, fields, timeout):
    """application/x-www-form-urlencoded POST → (HTTP 상태, 응답 JSON dict). 연결 실패는 OSError.

    테스트에서 바꿔 끼운다. 요청·응답 내용(인가 코드, 토큰)은 로그에 남기지 않는다.
    """
    data = urllib.parse.urlencode(fields).encode("ascii")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            status, raw = res.status, res.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {}
    return status, payload if isinstance(payload, dict) else {}


def provider_name_from_id_token(id_token):
    """id_token의 identities[0].providerName만 읽는다. 못 읽으면 None.

    화면에 보일 이름을 고르는 표시용이다. 서명은 여기서 검증하지 않는다.
    API 호출 권한은 API Gateway JWT authorizer가 액세스 토큰의 서명을 검증해서 정한다.
    다른 클레임(이메일, 제공자 쪽 사용자 ID 등)은 읽지 않는다.
    """
    try:
        part = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        identities = claims.get("identities")
        if isinstance(identities, str):
            identities = json.loads(identities)
        name = identities[0].get("providerName")
        return name if isinstance(name, str) else None
    except Exception:  # noqa: BLE001 — 표시용이라 못 읽으면 기본 문구
        return None


def h_social_providers(event):
    config = social_config()
    if not config:
        return 200, {"providers": []}
    return 200, {"providers": [{"id": pid, "label": SOCIAL_LABELS[pid][0]} for pid in config[2]]}


def h_social_start(event):
    data = body(event)
    provider = data.get("provider")
    if not isinstance(provider, str) or provider not in SOCIAL_LABELS:
        raise TeamError(400, "INVALID_INPUT", "지원하지 않는 로그인 방법이에요.")
    redirect_uri = redirect_uri_field(data)
    state = text_field(data, "state", STATE_VALUE, "state 형식이 올바르지 않아요.")
    challenge = text_field(data, "codeChallenge", PKCE_VALUE, "codeChallenge 형식이 올바르지 않아요.")
    domain, client_id, providers = require_social_config()
    if provider not in providers:
        raise TeamError(400, "INVALID_INPUT", "지원하지 않는 로그인 방법이에요.")
    query = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "identity_provider": providers[provider],
        "scope": "openid",
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return 200, {"authorizeUrl": f"https://{domain}/oauth2/authorize?{query}"}


def h_social_token(event):
    data = body(event)
    code = text_field(data, "code", CODE_VALUE, "code 형식이 올바르지 않아요.")
    redirect_uri = redirect_uri_field(data)
    verifier = text_field(data, "codeVerifier", PKCE_VALUE, "codeVerifier 형식이 올바르지 않아요.")
    domain, client_id, providers = require_social_config()
    try:
        status, result = post_form(f"https://{domain}/oauth2/token", {
            "grant_type": "authorization_code", "client_id": client_id, "code": code,
            "redirect_uri": redirect_uri, "code_verifier": verifier,
        }, SOCIAL_TIMEOUT_SECONDS)
    except OSError:  # 연결 실패, 타임아웃 (URLError·TimeoutError 모두 OSError)
        raise TeamError(503, "AWS_SERVICE_ERROR", "로그인을 처리하지 못했어요.", True)
    if status == 429:
        raise TeamError(429, "RATE_LIMITED", "잠시 후 다시 시도해 주세요.", True)
    if 400 <= status < 500:  # invalid_grant(코드가 틀림·만료·이미 씀, verifier 불일치) 등
        raise TeamError(401, "INVALID_CREDENTIALS", "로그인이 만료됐거나 올바르지 않아요. 다시 시도해 주세요.")
    access, id_token, expires = result.get("access_token"), result.get("id_token"), result.get("expires_in")
    if status != 200 or not isinstance(access, str) or not isinstance(id_token, str) or not isinstance(expires, int):
        raise TeamError(503, "AWS_SERVICE_ERROR", "로그인을 처리하지 못했어요.", True)
    out = {"accessToken": access, "idToken": id_token, "expiresIn": expires, "tokenType": "Bearer"}
    if isinstance(result.get("refresh_token"), str):
        out["refreshToken"] = result["refresh_token"]
    by_cognito_name = {name: pid for pid, name in providers.items()}
    pid = by_cognito_name.get(provider_name_from_id_token(id_token))
    out["username"] = SOCIAL_LABELS[pid][1] if pid else SOCIAL_FALLBACK_NAME
    return 200, out


ROUTES = {
    ("POST", "/api/v1/auth/login"): h_login,
    ("POST", "/api/v1/auth/refresh"): h_refresh,
    ("GET", "/api/v1/me"): h_me,
    ("GET", "/api/v1/auth/social/providers"): h_social_providers,
    ("POST", "/api/v1/auth/social/start"): h_social_start,
    ("POST", "/api/v1/auth/social/token"): h_social_token,
}


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
    except Exception as e:  # noqa: BLE001 — 비밀번호·인가 코드·토큰이 담긴 요청이라 내용은 로그에 남기지 않음
        print(f"[ERROR] {method} {path} {request_id}: {type(e).__name__}")
        return error_response(TeamError(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요.", True), request_id)
