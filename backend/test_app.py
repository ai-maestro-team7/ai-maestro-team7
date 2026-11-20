"""라우터 테스트: uv run --no-project --python 3.13 --with boto3 python test_app.py"""

import json

from app import lambda_handler


def call(method, path):
    res = lambda_handler({"rawPath": path, "requestContext": {"http": {"method": method, "path": path}}}, None)
    return res["statusCode"], json.loads(res["body"]) if res["body"] else None


def is_team_error(body):
    return isinstance(body, dict) and set(body.get("error", {})) == {"code", "message", "requestId", "retryable"}


CASES = [
    ("GET /health", lambda: call("GET", "/health"), lambda s, b: s == 200 and b["ok"]),
    ("GET /api/v1/health", lambda: call("GET", "/api/v1/health"), lambda s, b: s == 200),
    ("OPTIONS → 204 (CORS 사전 요청)", lambda: call("OPTIONS", "/api/v1/interview/start"), lambda s, b: s == 204),
    ("없는 주소 → 404 팀 공통 오류 형식", lambda: call("GET", "/nope"), lambda s, b: s == 404 and is_team_error(b)),
    ("옛 mock 경로 /chat 제거됨 → 404", lambda: call("POST", "/chat"), lambda s, b: s == 404),
    ("A 경로 → 501 연결 예정", lambda: call("GET", "/api/v1/mentoring/profiles/me"), lambda s, b: s == 501 and is_team_error(b)),
    ("B 경로 → 501 연결 예정", lambda: call("GET", "/api/v1/opportunities/postings"), lambda s, b: s == 501),
    ("공통 프로필 경로 → 프로필 처리로 (userId 없으면 401)", lambda: call("GET", "/api/v1/me/profile"), lambda s, b: s == 401 and is_team_error(b)),
    ("면접 경로는 면접 처리로 (userId 없으면 401)", lambda: call("GET", "/api/v1/interview/00000000-0000-0000-0000-000000000000/status"),
     lambda s, b: s == 401 and is_team_error(b)),
]

ok = 0
for name, run, expect in CASES:
    s, b = run()
    passed = bool(expect(s, b))
    ok += passed
    print(f"{'PASS' if passed else 'FAIL'} {name} ({s})")
print(f"\n{ok}/{len(CASES)} 통과")
raise SystemExit(0 if ok == len(CASES) else 1)
