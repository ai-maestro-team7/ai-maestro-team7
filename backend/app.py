"""team07 API — Lambda 진입점 (HTTP API payload v2.0).

경로 앞부분으로 파트별 처리로 나눈다 (docs/api.md):
  /api/v1/interview/*      모의면접 (C)          → interview_api.py
  /api/v1/mentoring/*      멘토링 (A)            → mentoring_api.py
  /api/v1/opportunities/*  부산 기회 추천 (B)    → opportunities_api.py
  /api/v1/auth/login·refresh 로그인 (토큰 없이)  → auth_api.py
  /api/v1/me               내 정보 (토큰 필요)    → auth_api.py
  /api/v1/me/*             기본 프로필, 워크스페이스 → me_api.py, workspace.py
  /health, /api/v1/health  상태 확인

오류는 모두 팀 공통 형식 {error: {code, message, requestId, retryable}}.
"""

import importlib

from common import ALLOWED_ORIGIN, TeamError, error_response, json_response, new_request_id, now_iso


def part(module_name):
    """파트 처리 모듈을 불러온다. 아직 배포 묶음에 없으면 None (해당 경로만 501, 나머지는 정상)."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name != module_name:  # 모듈 안의 다른 import 실패는 숨기지 않는다
            raise
        return None


def not_implemented():
    return error_response(TeamError(501, "NOT_IMPLEMENTED", "아직 연결되지 않은 기능이에요.", False), new_request_id())


def dispatch(module_name, event, method, path):
    mod = part(module_name)
    return mod.handle(event, method, path) if mod else not_implemented()


def health():
    interview = part("interview_api")
    opportunities = part("opportunities_api")
    return json_response(200, {"ok": True, "time": now_iso(), "interviewImpl": interview.IMPL_NAME if interview else None,
                               "opportunitiesImpl": opportunities.IMPL_NAME if opportunities else None})


def lambda_handler(event, context):
    # 뒤에서 처리하는 작업 (Lambda 비동기 자기 호출)
    if "mentoringTask" in event:
        return part("mentoring_api").run_task(event)
    if "task" in event:
        return part("interview_api").run_task(event)
    # B 정기 수집 (EventBridge Scheduler → 출처별 비동기 자기 호출)
    if "oppBatch" in event:
        return part("opportunities_api").run_batch(event)
    # B 알림 일정 (EventBridge Scheduler)
    if "oppSchedule" in event:
        return part("opportunities_api").run_schedule(event)
    # 통합 Agent의 Action Group 호출 (Bedrock Agents). API Gateway를 거치지 않는다
    if event.get("actionGroup") == "BusanOpportunity" and "messageVersion" in event:
        return part("opportunities_api").handle_agent(event)

    http = event.get("requestContext", {}).get("http", {})
    method = http.get("method", "GET")
    path = (event.get("rawPath") or http.get("path") or "/").rstrip("/") or "/"

    if method == "OPTIONS":
        return {"statusCode": 204, "headers": {"Access-Control-Allow-Origin": ALLOWED_ORIGIN}, "body": ""}
    if path in ("/health", "/api/v1/health") and method == "GET":
        return health()
    if path.startswith("/api/v1/me/"):
        return dispatch("me_api", event, method, path)
    if path.startswith("/api/v1/auth/") or path == "/api/v1/me":
        return dispatch("auth_api", event, method, path)
    if path.startswith("/api/v1/interview/"):
        return dispatch("interview_api", event, method, path)
    if path.startswith("/api/v1/mentoring/") or path == "/api/v1/mentoring":
        return dispatch("mentoring_api", event, method, path)
    if path.startswith("/api/v1/opportunities/"):
        return dispatch("opportunities_api", event, method, path)
    if path.startswith("/api/v1/opportunities"):
        return not_implemented()
    return error_response(TeamError(404, "NOT_FOUND", "없는 주소예요."), new_request_id())
