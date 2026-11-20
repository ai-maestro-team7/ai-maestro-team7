"""채팅 Agent 백엔드 연결 — /api/v1/agent/* (D-38, docs/개발계획서4.md §7)

  POST /api/v1/agent/chat                                   {sessionId?, message, attachments?} → 202 {sessionId, messageId, status}
  GET  /api/v1/agent/chat/{sessionId}                       대화와 메시지 목록
  GET  /api/v1/agent/chat/{sessionId}/messages/{messageId}  Agent 답 하나 (화면이 2초마다 조회)
  run_task                                                  `agentTask` 이벤트 (Lambda 비동기 자기 호출, D-19)

역할 분담:
  여기(백엔드) = 사용자 확인, 포트 구현(B 함수, DynamoDB 읽기), 비동기 자기 호출
  supervisor 패키지(ai/supervisor/) = 도구 정의, 한 턴 실행, 답 검사, 카드·행동 조립
도구에는 userId 인자가 없다. 토큰의 sub만 포트에 넘긴다.
"""

import json
import os
import re
from functools import lru_cache

import boto3

from common import TeamError, error_response, get_user_id, hash_user_id, json_response, new_request_id, to_plain

try:  # infra/package.sh가 ai/supervisor/src/supervisor/를 `supervisor`로 묶는다
    from supervisor import service
    from supervisor.deps import Deps
    from supervisor.errors import SupervisorError
    from supervisor.models import DocumentInfo
    from supervisor.store.dynamo import DynamoChatStore

    IMPL_NAME = "supervisor"
except ImportError:  # 배포 묶음에 없으면 /api/v1/agent/*만 501
    IMPL_NAME = None

TABLE = os.environ.get("TABLE_CAREER_MENTOR", "team07-career-mentor")
REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
TEXT_STATUSES = {"EXTRACTED", "ANALYZING", "REQUIRES_USER_REVIEW", "COMPLETED"}  # 정규화 텍스트가 있는 A 문서 상태
NOT_SKILL = {"NOT_FOUND", "USER_CONFIRMED_GAP"}  # 검색 질의에 넣지 않는 역량 (서류에 없음, 미보유 확인)
MAX_RESUME_TERMS = 15


@lru_cache(maxsize=1)
def table():
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE)


def pk(user_id):
    return f"USER#{user_id}"


# ---------------------------------------------------------------- 포트 구현
class OpportunityAdapter:
    """B `opportunity.api.agent_handler`의 두 입구 공용 함수를 부른다 (Bedrock Action Group 경로와 같은 함수)."""

    def _b(self):
        import opportunities_api

        if opportunities_api.IMPL_NAME is None:
            raise TeamError(501, "NOT_IMPLEMENTED", "공고·정책 기능이 아직 연결되지 않았어요.")
        from opportunity.api import agent_handler

        return opportunities_api.deps(), agent_handler

    def search_postings(self, user_id, *, job_name, keyword, organization, region, min_salary, career_type,
                        query_terms):
        deps, handler = self._b()
        return handler.agent_feed(deps, user_id, keyword=keyword, region=region, job_name=job_name,
                                  query_terms=query_terms, min_salary=min_salary, career_type=career_type,
                                  organization=organization).to_api()

    def match_policies(self, user_id, *, stage):
        deps, handler = self._b()
        return handler.agent_policy_list(deps, user_id, stage=stage).to_api()

    def ask_policies(self, user_id, question):
        deps, _ = self._b()
        from opportunity.enrich.ask import ask_policies

        return ask_policies(deps, user_id, question).to_api()

    def profile_region_code(self, region):
        """기본 프로필 desiredRegion 값. 부산 → 26, 전국 → ALL, 시·도 → 코드. 수도권·해외처럼 코드 하나로 못 적으면 None."""
        try:
            deps, handler = self._b()
            value = handler.resolve_region(region)
        except Exception:  # noqa: BLE001 - 못 바꾸면 저장 묻기에서 지역만 뺀다
            return None
        if value == "BUSAN":
            return deps.config.data.busan_sido
        if value == "ALL" or re.fullmatch(r"\d{2}", value or ""):
            return value
        return None


class CareerDocsAdapter:
    """A가 쓴 `DOC_LATEST#`·`PROFILE#LATEST`를 읽기만 한다. 원문·S3 키는 Agent에 넘기지 않는다."""

    def latest_documents(self, user_id):
        from boto3.dynamodb.conditions import Key

        items, start = [], None
        while True:
            kwargs = {"KeyConditionExpression": Key("PK").eq(pk(user_id)) & Key("SK").begins_with("DOC_LATEST#")}
            if start:
                kwargs["ExclusiveStartKey"] = start
            page = table().query(**kwargs)
            items += page.get("Items", [])
            start = page.get("LastEvaluatedKey")
            if not start:
                break
        docs = []
        for item in map(to_plain, items):
            if item.get("ownerUserId", user_id) != user_id or not item.get("documentId"):
                continue
            status = item.get("extractionStatus") or "PENDING"
            docs.append(DocumentInfo(document_id=item["documentId"], document_type=item.get("documentType") or "RESUME",
                                     title=item.get("title"), status=status,
                                     has_text=bool(item.get("extractedTextKey")) or status in TEXT_STATUSES,
                                     updated_at=item.get("updatedAt")))
        return docs

    def resume_terms(self, user_id):
        latest = table().get_item(Key={"PK": pk(user_id), "SK": "PROFILE#LATEST"}).get("Item")
        if not latest:
            return []
        version = int(latest["latestVersion"])
        item = table().get_item(Key={"PK": pk(user_id),
                                     "SK": f"PROFILE#{latest['latestProfileId']}#V#{version:04d}"}).get("Item")
        skills = (to_plain(item) or {}).get("skills") or [] if item else []
        terms = []
        for skill in skills:
            name = (skill.get("name") or "").strip()
            if name and skill.get("evidenceLevel") not in NOT_SKILL and name not in terms:
                terms.append(name[:50])
            if len(terms) == MAX_RESUME_TERMS:
                break
        return terms


class ProfileAdapter:
    def get_basic_profile(self, user_id):
        item = table().get_item(Key={"PK": pk(user_id), "SK": "PROFILE#BASIC"}).get("Item")
        if not item:
            return None
        return {k: v for k, v in to_plain(item).items() if k not in ("PK", "SK", "ownerUserId", "entityType")}


class SelfInvokeDispatcher:
    """SQS 대신 Lambda 비동기 자기 호출 (D-19). Lambda 밖이나 RUN_TASKS_INLINE=1이면 바로 실행."""

    def __init__(self):
        self._client = None

    def dispatch(self, event):
        fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        if not fn or os.environ.get("RUN_TASKS_INLINE") == "1":
            run_task(event)
            return
        if self._client is None:
            self._client = boto3.client("lambda", region_name=REGION)
        response = self._client.invoke(FunctionName=fn, InvocationType="Event",
                                       Payload=json.dumps(event, ensure_ascii=False).encode("utf-8"))
        if response.get("StatusCode") != 202:
            raise TeamError(503, "AWS_SERVICE_ERROR", "답변 작업을 시작하지 못했어요. 다시 보내 주세요.", True)


_deps = None


def build_runner():
    from supervisor.config import get_config
    from supervisor.runner import StrandsRunner

    return StrandsRunner(model_id=model_id(), region=REGION, config=get_config())


def model_id():
    value = os.environ.get("MODEL_ID", "").strip()
    if not value:
        raise TeamError(501, "NOT_IMPLEMENTED", "채팅 모델 설정이 없어요.")
    return value


def deps():
    """Lambda 컨테이너마다 한 번만 만든다."""
    global _deps
    if _deps is None:
        _deps = Deps(store=DynamoChatStore(table()), opportunities=OpportunityAdapter(), docs=CareerDocsAdapter(),
                     profiles=ProfileAdapter(), runner=build_runner(), dispatcher=SelfInvokeDispatcher(),
                     model_id=model_id(), hash_user_id=lambda u: hash_user_id(u)[:16])
    return _deps


# ---------------------------------------------------------------- 경로
def parse_json(event):
    import base64

    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.") from None
    if not isinstance(data, dict):
        raise TeamError(400, "INVALID_INPUT", "요청 형식이 올바르지 않아요.")
    return {k: v for k, v in data.items() if k != "userId"}  # 본문의 userId는 쓰지 않는다


def h_chat(event, user_id, params):
    return 202, service.start_turn(deps(), user_id, parse_json(event))


def h_session(event, user_id, params):
    return 200, service.get_session(deps(), user_id, params["sessionId"])


def h_message(event, user_id, params):
    return 200, service.get_message(deps(), user_id, params["sessionId"], params["messageId"])


ROUTES = [
    ("POST", r"/api/v1/agent/chat", h_chat),
    ("GET", r"/api/v1/agent/chat/(?P<sessionId>[^/]+)", h_session),
    ("GET", r"/api/v1/agent/chat/(?P<sessionId>[^/]+)/messages/(?P<messageId>[^/]+)", h_message),
]


def handle(event, method, path):
    request_id = new_request_id()
    if IMPL_NAME is None:
        return error_response(TeamError(501, "NOT_IMPLEMENTED", "아직 연결되지 않은 기능이에요."), request_id)
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
    except SupervisorError as e:
        return error_response(TeamError(e.status, e.code, e.message, e.retryable), request_id)
    except Exception as e:  # noqa: BLE001
        print(f"[ERROR] {method} {path} {request_id}: {type(e).__name__}")
        return error_response(TeamError(500, "INTERNAL_ERROR", "일시적인 오류가 발생했어요. 잠시 후 다시 시도해 주세요.", True),
                              request_id)


def run_task(event):
    """`agentTask` 이벤트. 결과는 메시지 상태로 남기고 예외를 던지지 않는다."""
    if IMPL_NAME is None:
        raise RuntimeError("채팅 Agent 패키지가 배포되지 않았습니다")
    return service.run_turn(deps(), event.get("agentTask") or {})
