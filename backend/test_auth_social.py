"""소셜 로그인 테스트 (가짜 HTTP, AWS·네트워크 호출 없음).

실행: cd backend && uv run --no-project --python 3.13 --with boto3 python test_auth_social.py
"""

import base64
import contextlib
import io
import json
import os
import urllib.parse

os.environ.update(AWS_DEFAULT_REGION="ap-northeast-2", AWS_REGION="ap-northeast-2")
for key in ("COGNITO_DOMAIN", "SOCIAL_PROVIDERS", "COGNITO_CLIENT_ID"):
    os.environ.pop(key, None)

import auth_api  # noqa: E402
from app import lambda_handler  # noqa: E402

DOMAIN = "example-auth.auth.ap-northeast-2.amazoncognito.com"
CLIENT = "test-client-id"
REDIRECT = "https://web.example.test/login/callback/"
STATE = "s" * 43
CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CODE = "secret-auth-code-1234"
ACCESS = "eyJ.access-token-value.sig"
REFRESH = "refresh-token-value"

results = []


def check(name, cond):
    cond = bool(cond)
    results.append(cond)
    print(f"{'PASS' if cond else 'FAIL'} {name}")


def configure(providers="google=Google,kakao=Kakao", domain=DOMAIN, client=CLIENT):
    for key, value in (("SOCIAL_PROVIDERS", providers), ("COGNITO_DOMAIN", domain), ("COGNITO_CLIENT_ID", client)):
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def call(method, path, payload=None):
    event = {"rawPath": path, "requestContext": {"http": {"method": method, "path": path}}}
    if payload is not None:
        event["body"] = json.dumps(payload)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        res = lambda_handler(event, None)
    return res["statusCode"], json.loads(res["body"]) if res["body"] else None, out.getvalue()


def error_code(b):
    return (b or {}).get("error", {}).get("code")


def is_team_error(b):
    return isinstance(b, dict) and set(b.get("error", {})) == {"code", "message", "requestId", "retryable"}


def id_token(claims):
    def seg(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{seg({'alg': 'RS256'})}.{seg(claims)}.sig"


def start_body(**kw):
    return {"provider": "google", "redirectUri": REDIRECT, "state": STATE, "codeChallenge": CHALLENGE, **kw}


def token_body(**kw):
    return {"code": CODE, "redirectUri": REDIRECT, "codeVerifier": VERIFIER, **kw}


class FakeHttp:
    def __init__(self, status=200, payload=None, exc=None):
        self.status, self.payload, self.exc, self.calls = status, payload or {}, exc, []

    def __call__(self, url, fields, timeout):
        self.calls.append((url, dict(fields), timeout))
        if self.exc:
            raise self.exc
        return self.status, self.payload


def with_http(fake):
    original = auth_api.post_form
    auth_api.post_form = fake
    return original


# ---------------------------------------------------------------- providers
configure(providers=None, domain=None, client=None)
s, b, _ = call("GET", "/api/v1/auth/social/providers")
check("providers: 설정 없음 → 200 빈 목록", s == 200 and b == {"providers": []})

configure(domain=None)
s, b, _ = call("GET", "/api/v1/auth/social/providers")
check("providers: 도메인만 없어도 빈 목록", s == 200 and b == {"providers": []})

configure(providers=None)
s, b, _ = call("GET", "/api/v1/auth/social/providers")
check("providers: 제공자만 없어도 빈 목록", s == 200 and b == {"providers": []})

configure(domain="https://evil.test/path")
s, b, _ = call("GET", "/api/v1/auth/social/providers")
check("providers: 도메인이 호스트 이름이 아니면 빈 목록", s == 200 and b == {"providers": []})

configure()
s, b, _ = call("GET", "/api/v1/auth/social/providers")
check("providers: 설정됨 → Google·카카오", s == 200 and b == {
    "providers": [{"id": "google", "label": "Google"}, {"id": "kakao", "label": "카카오"}]})

configure(providers="kakao=Kakao,facebook=Facebook")
s, b, _ = call("GET", "/api/v1/auth/social/providers/")
check("providers: 모르는 id는 빼고, 끝 / 도 같은 경로", s == 200 and b == {"providers": [{"id": "kakao", "label": "카카오"}]})

# ---------------------------------------------------------------- start
configure()
s, b, _ = call("POST", "/api/v1/auth/social/start", start_body())
url = urllib.parse.urlsplit((b or {}).get("authorizeUrl", ""))
q = dict(urllib.parse.parse_qsl(url.query))
check("start: 200, https://{도메인}/oauth2/authorize",
      s == 200 and url.scheme == "https" and url.netloc == DOMAIN and url.path == "/oauth2/authorize")
check("start: URL 파라미터 전부", q == {
    "response_type": "code", "client_id": CLIENT, "redirect_uri": REDIRECT, "identity_provider": "Google",
    "scope": "openid", "state": STATE, "code_challenge": CHALLENGE, "code_challenge_method": "S256"})

s, b, _ = call("POST", "/api/v1/auth/social/start", start_body(provider="kakao"))
q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(b["authorizeUrl"]).query))
check("start: 카카오 → identity_provider=Kakao", s == 200 and q["identity_provider"] == "Kakao")

s, b, _ = call("POST", "/api/v1/auth/social/start", start_body(redirectUri="http://localhost:3000/login/callback/"))
check("start: 로컬 개발 http://localhost 허용", s == 200)

bad_starts = [
    ("모르는 provider", start_body(provider="facebook")),
    ("provider 빠짐", {k: v for k, v in start_body().items() if k != "provider"}),
    ("provider가 문자열이 아님", start_body(provider=["google"])),
    ("redirectUri http (localhost 아님)", start_body(redirectUri="http://web.example.test/login/callback/")),
    ("redirectUri http://localhost.evil.test", start_body(redirectUri="http://localhost.evil.test/login/callback/")),
    ("redirectUri 경로가 다름", start_body(redirectUri="https://web.example.test/login/")),
    ("redirectUri 끝 / 없음", start_body(redirectUri="https://web.example.test/login/callback")),
    ("redirectUri 쿼리 붙음", start_body(redirectUri="https://web.example.test/login/callback/?x=1")),
    ("redirectUri 조각 붙음", start_body(redirectUri="https://web.example.test/login/callback/#x")),
    ("redirectUri 사용자 정보 붙음", start_body(redirectUri="https://a@web.example.test/login/callback/")),
    ("redirectUri javascript:", start_body(redirectUri="javascript:alert(1)//login/callback/")),
    ("redirectUri 빠짐", {k: v for k, v in start_body().items() if k != "redirectUri"}),
    ("codeChallenge 짧음", start_body(codeChallenge="abc")),
    ("codeChallenge 129자", start_body(codeChallenge="a" * 129)),
    ("codeChallenge 허용 안 되는 문자", start_body(codeChallenge=CHALLENGE[:-1] + "+")),
    ("codeChallenge 빠짐", {k: v for k, v in start_body().items() if k != "codeChallenge"}),
    ("state 허용 안 되는 문자", start_body(state="a" * 42 + "&")),
    ("state 짧음", start_body(state="abc")),
    ("state 빠짐", {k: v for k, v in start_body().items() if k != "state"}),
]
for name, payload in bad_starts:
    s, b, _ = call("POST", "/api/v1/auth/social/start", payload)
    check(f"start: {name} → 400 INVALID_INPUT", s == 400 and error_code(b) == "INVALID_INPUT" and is_team_error(b))

s, b, _ = call("POST", "/api/v1/auth/social/start", None)
check("start: 본문 없음 → 400", s == 400 and error_code(b) == "INVALID_INPUT")

configure(providers="kakao=Kakao")
s, b, _ = call("POST", "/api/v1/auth/social/start", start_body())
check("start: 설정에 없는 제공자(google) → 400", s == 400 and error_code(b) == "INVALID_INPUT")

configure(providers=None, domain=None)
s, b, _ = call("POST", "/api/v1/auth/social/start", start_body())
check("start: 설정 없음 → 503 AWS_SERVICE_ERROR", s == 503 and error_code(b) == "AWS_SERVICE_ERROR" and b["error"]["retryable"])

configure(client=None)
auth_api.CLIENT_ID = ""
s, b, _ = call("POST", "/api/v1/auth/social/start", start_body())
check("start: 앱 클라이언트 ID 없음 → 503", s == 503 and error_code(b) == "AWS_SERVICE_ERROR")

# ---------------------------------------------------------------- token
configure()
good = FakeHttp(200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600, "token_type": "Bearer",
                      "id_token": id_token({"sub": "u1", "email": "someone@example.test",
                                            "identities": [{"providerName": "Google", "userId": "g-123"}]})})
original = with_http(good)
s, b, logs = call("POST", "/api/v1/auth/social/token", token_body())
check("token: 성공 → 200 로그인 응답 모양 + username", s == 200 and b["accessToken"] == ACCESS and b["refreshToken"] == REFRESH
      and b["expiresIn"] == 3600 and b["tokenType"] == "Bearer" and b["idToken"] and b["username"] == "Google 계정")
check("token: 응답 키는 계약 그대로",
      set(b) == {"accessToken", "idToken", "refreshToken", "expiresIn", "tokenType", "username"})
url, fields, timeout = good.calls[0]
check("token: https://{도메인}/oauth2/token 에 5초 타임아웃", url == f"https://{DOMAIN}/oauth2/token" and timeout == 5)
check("token: 보낸 값 (grant_type, client_id, code, redirect_uri, code_verifier)", fields == {
    "grant_type": "authorization_code", "client_id": CLIENT, "code": CODE, "redirect_uri": REDIRECT,
    "code_verifier": VERIFIER})
check("token: 이메일 같은 개인정보는 응답에 없음", "someone@example.test" not in json.dumps(b, ensure_ascii=False).replace(b["idToken"], ""))

kakao = FakeHttp(200, dict(good.payload, id_token=id_token({"identities": json.dumps([{"providerName": "Kakao"}])})))
with_http(kakao)
s, b, _ = call("POST", "/api/v1/auth/social/token", token_body())
check("token: identities가 문자열이어도 카카오 계정", s == 200 and b["username"] == "카카오 계정")

for name, tok in (("id_token 형식이 아님", "not-a-jwt"), ("identities 없음", id_token({"sub": "u1"})),
                  ("모르는 제공자 이름", id_token({"identities": [{"providerName": "Apple"}]}))):
    with_http(FakeHttp(200, dict(good.payload, id_token=tok)))
    s, b, _ = call("POST", "/api/v1/auth/social/token", token_body())
    check(f"token: {name} → username 소셜 계정", s == 200 and b["username"] == "소셜 계정")

with_http(FakeHttp(400, {"error": "invalid_grant"}))
s, b, logs = call("POST", "/api/v1/auth/social/token", token_body())
check("token: invalid_grant → 401 INVALID_CREDENTIALS", s == 401 and error_code(b) == "INVALID_CREDENTIALS"
      and not b["error"]["retryable"] and is_team_error(b))
check("token: 401 응답에 인가 코드를 되돌려 보내지 않음", CODE not in json.dumps(b))

with_http(FakeHttp(429, {}))
s, b, _ = call("POST", "/api/v1/auth/social/token", token_body())
check("token: 429 → RATE_LIMITED", s == 429 and error_code(b) == "RATE_LIMITED")

for name, fake in (("연결 실패", FakeHttp(exc=OSError("connection refused"))),
                   ("타임아웃", FakeHttp(exc=TimeoutError("timed out"))),
                   ("Cognito 500", FakeHttp(500, {})),
                   ("200인데 토큰 없음", FakeHttp(200, {"token_type": "Bearer"}))):
    with_http(fake)
    s, b, _ = call("POST", "/api/v1/auth/social/token", token_body())
    check(f"token: {name} → 503 AWS_SERVICE_ERROR (retryable)",
          s == 503 and error_code(b) == "AWS_SERVICE_ERROR" and b["error"]["retryable"])

calls = FakeHttp(200, good.payload)
with_http(calls)
for name, payload in (("code 빠짐", {k: v for k, v in token_body().items() if k != "code"}),
                      ("code 허용 안 되는 문자", token_body(code="a&b=c")),
                      ("codeVerifier 짧음", token_body(codeVerifier="short")),
                      ("redirectUri 경로가 다름", token_body(redirectUri="https://web.example.test/other/"))):
    s, b, _ = call("POST", "/api/v1/auth/social/token", payload)
    check(f"token: {name} → 400 INVALID_INPUT", s == 400 and error_code(b) == "INVALID_INPUT")
check("token: 입력이 틀리면 Cognito를 부르지 않음", calls.calls == [])

configure(domain=None)
s, b, _ = call("POST", "/api/v1/auth/social/token", token_body())
check("token: 설정 없음 → 503", s == 503 and error_code(b) == "AWS_SERVICE_ERROR")
configure()


# ---------------------------------------------------------------- 로그
def boom(url, fields, timeout):
    raise RuntimeError(f"unexpected {fields['code']} {fields['code_verifier']}")


all_logs = []
for fake in (good, FakeHttp(400, {"error": "invalid_grant"}), FakeHttp(exc=OSError(CODE)), boom):
    with_http(fake)
    s, b, logs = call("POST", "/api/v1/auth/social/token", token_body())
    all_logs.append(logs)
check("token: 예상 못 한 오류 → 500 INTERNAL_ERROR", s == 500 and error_code(b) == "INTERNAL_ERROR")
joined = "\n".join(all_logs)
check("로그: 인가 코드·code_verifier·토큰이 찍히지 않음",
      all(secret not in joined for secret in (CODE, VERIFIER, ACCESS, REFRESH, "g-123", "someone@example.test")))
check("로그: 예상 못 한 오류는 종류만 남김", "RuntimeError" in joined)
auth_api.post_form = original

# ---------------------------------------------------------------- 라우팅
s, b, _ = call("GET", "/api/v1/auth/social/start")
check("라우팅: start를 GET으로 부르면 404", s == 404 and is_team_error(b))
s, b, _ = call("DELETE", "/api/v1/auth/social/providers")
check("라우팅: providers를 DELETE로 부르면 404", s == 404)

print(f"\n{sum(results)}/{len(results)} 통과")
raise SystemExit(0 if all(results) else 1)
