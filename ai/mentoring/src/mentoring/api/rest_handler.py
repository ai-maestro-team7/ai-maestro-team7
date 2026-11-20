"""REST 입구 `/api/v1/mentoring/*` (개발계획서1 §6.1).
API Gateway는 HTTP API(payload v2.0)라서 `APIGatewayHttpResolver`를 쓴다 (docs/api.md §1).
user_id와 Deps는 백엔드가 넣어 준다(`backend/mentoring_api.py`, BE-1). 요청 본문·쿼리의 userId는 쓰지 않는다.
여기서는 요청을 모델로 바꾸고 비즈니스 함수를 부를 뿐 규칙을 두지 않는다 (Requirement 1 기준 2).
"""
import json
import logging
import time
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from pydantic import ValidationError

from ..core.documents import create_text_document, get_document
from ..core.logs import log_event, user_hash
from ..core.profiles import confirm_profile, get_latest_profile
from ..core.upload import complete_upload, create_upload_url
from ..deps import Deps
from ..errors import MentoringError, invalid_input, not_implemented, unauthorized
from ..models import ConfirmRequest, TextDocumentRequest, UploadUrlRequest
from ..fit.analysis import analysis_view, create_analysis, get_analysis
from ..fit.records import AnalysisRequest
from ..stories import AnswerStoryRequest, CreateStoryRequest, get_story, list_stories
from ..stories.flow import start_story, story_view, update_story
from . import errors

PREFIX = "/api/v1/mentoring"
logger = logging.getLogger("mentoring.api")


def _dumps(body: Any) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


app = APIGatewayHttpResolver(serializer=_dumps)


# ---------------------------------------------------------------- 요청 도우미
def _deps() -> Deps:
    return app.context["deps"]


def _user_id() -> str:
    return app.context["user_id"]


def _request_id() -> str:
    try:
        return app.current_event.request_context.request_id or errors.new_request_id()
    except (AttributeError, KeyError, TypeError):
        return errors.new_request_id()


def _body(model):
    raw = app.current_event.decoded_body
    if not raw:
        raise invalid_input("요청 본문이 없어요.")
    try:
        data = json.loads(raw)
    except ValueError:
        raise invalid_input("요청 본문이 JSON 형식이 아니에요.") from None
    if not isinstance(data, dict):
        raise invalid_input("요청 본문은 JSON 객체여야 해요.")
    return model.model_validate(data)


def _header(name: str) -> str | None:
    headers = app.current_event.headers or {}
    lowered = name.lower()
    return next((v for k, v in headers.items() if k.lower() == lowered), None)


def _id(value: str, field: str) -> str:
    """주소의 ID. `#`이 들어가면 400 (docs/api.md §2)."""
    if not value or "#" in value or "%23" in value.lower():
        raise invalid_input("ID 형식이 올바르지 않아요.", field=field)
    return value


def _json(status: int, body: dict) -> Response:
    return Response(status_code=status, content_type="application/json", body=body)


# ---------------------------------------------------------------- 문서
@app.post(f"{PREFIX}/documents/upload-url")
def rest_create_upload_url():
    body = create_upload_url(_deps(), _user_id(), _body(UploadUrlRequest), _header("Idempotency-Key"))
    return _json(201, body)


@app.post(f"{PREFIX}/documents/<document_id>/complete")
def rest_complete_upload(document_id: str):
    return _json(202, complete_upload(_deps(), _user_id(), _id(document_id, "documentId")))


@app.post(f"{PREFIX}/documents/text")
def rest_create_text_document():
    body = create_text_document(_deps(), _user_id(), _body(TextDocumentRequest), _header("Idempotency-Key"))
    return _json(202, body)


@app.get(f"{PREFIX}/documents/<document_id>")
def rest_get_document(document_id: str):
    return get_document(_deps(), _user_id(), _id(document_id, "documentId")).to_api()


# ---------------------------------------------------------------- 역량 프로필
@app.get(f"{PREFIX}/profiles/me")
def rest_get_profile():
    return get_latest_profile(_deps(), _user_id()).to_view()


@app.post(f"{PREFIX}/profiles/<profile_id>/confirm")
def rest_confirm_profile(profile_id: str):
    profile = confirm_profile(_deps(), _user_id(), _id(profile_id, "profileId"), _body(ConfirmRequest))
    return _json(201, profile.to_view())


# ---------------------------------------------------------------- 경험 블록 (Requirement 9, A F-01B)
# 질문 생성은 동기라서 POST는 202가 아니라 201로 결과를 돌려준다 (미결정 M-7, stories/flow.py)
@app.post(f"{PREFIX}/stories")
def rest_create_story():
    story = start_story(_deps(), _user_id(), _body(CreateStoryRequest), _header("Idempotency-Key"))
    return _json(201, story_view(story))


@app.get(f"{PREFIX}/stories")
def rest_list_stories():
    items = list_stories(_deps(), _story_repo(), _user_id())
    return {"stories": [{k: v for k, v in item.to_api().items() if k != "ownerUserId"} for item in items]}


@app.get(f"{PREFIX}/stories/<story_id>")
def rest_get_story(story_id: str):
    return story_view(get_story(_deps(), _story_repo(), _user_id(), _id(story_id, "storyId")))


@app.patch(f"{PREFIX}/stories/<story_id>")
def rest_update_story(story_id: str):
    story, warnings = update_story(_deps(), _user_id(), _id(story_id, "storyId"), _body(AnswerStoryRequest))
    return story_view(story, warnings)


def _story_repo():
    if _deps().stories is None:
        raise not_implemented()
    return _deps().stories


# ---------------------------------------------------------------- 직무 적합도 (mentoring-fit-review-learning Req 1~8)
@app.post(f"{PREFIX}/analyses")
def rest_create_analysis():
    body = create_analysis(_deps(), _user_id(), _body(AnalysisRequest), _header("Idempotency-Key"))
    return _json(202, body)


@app.get(f"{PREFIX}/analyses/<analysis_id>")
def rest_get_analysis(analysis_id: str):
    return analysis_view(get_analysis(_deps(), _user_id(), _id(analysis_id, "analysisId")))


# ---------------------------------------------------------------- 아직 만들지 않은 경로 (개발계획서1 §6.1)
_LATER = [
    ("POST", "/reviews"), ("GET", "/reviews/<review_id>"),
    ("POST", "/learning-paths"), ("GET", "/learning-paths/<learning_path_id>"),
    ("POST", "/agent/chat"), ("GET", "/health/readiness"),
]


def _later(**_):
    raise not_implemented()


for _method, _path in _LATER:
    app.route(f"{PREFIX}{_path}", method=_method)(_later)


# ---------------------------------------------------------------- 오류
@app.exception_handler(MentoringError)
def _on_mentoring_error(error: MentoringError):
    return _json(*errors.from_mentoring_error(error, _request_id()))


@app.exception_handler(ValidationError)
def _on_validation_error(error: ValidationError):
    return _json(*errors.from_validation_error(error, _request_id()))


@app.exception_handler(Exception)
def _on_unexpected(error: Exception):
    logger.error(json.dumps({"requestId": _request_id(), "errorType": type(error).__name__}))
    return _json(*errors.from_unexpected(_request_id()))


@app.not_found
def _on_not_found(error: NotFoundError):
    return _json(*errors.error_body(404, "NOT_FOUND", "찾을 수 없는 경로예요.", _request_id()))


# ---------------------------------------------------------------- 입구
def handle(event: dict, deps: Deps, user_id: str, context: Any = None) -> dict:
    """백엔드 Lambda가 부르는 입구. user_id는 토큰의 sub이고, 요청 안의 userId는 보지 않는다."""
    started = time.perf_counter()
    request_context = event.get("requestContext") or {}
    if not isinstance(user_id, str) or not user_id.strip():
        status, body = errors.from_mentoring_error(unauthorized(), request_context.get("requestId")
                                                   or errors.new_request_id())
        return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": _dumps(body)}
    app.append_context(deps=deps, user_id=user_id)
    response = app.resolve(event, context)
    http = request_context.get("http") or {}
    # 로그에는 requestId, 사용자 해시, 경로, 처리 시간, 오류 코드만 남긴다
    log_event("http.request", requestId=request_context.get("requestId"), userHash=user_hash(deps, user_id),
              method=http.get("method"), route=event.get("rawPath"), status=response.get("statusCode"),
              durationMs=round((time.perf_counter() - started) * 1000, 1),
              errorCode=errors.error_code_of(response.get("body")))
    return response
