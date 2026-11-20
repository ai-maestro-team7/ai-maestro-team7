"""REST 입구 `/api/v1/opportunities/*` (개발계획서2 §5.2 P0).

API Gateway는 HTTP API(payload v2.0)라서 `APIGatewayHttpResolver`를 쓴다 (docs/api.md §1).
userId와 Deps는 백엔드가 인증 정보에서 읽어 `handle`에 넣어 준다. 요청 본문·쿼리의 userId는 쓰지 않는다.
여기서는 요청을 모델로 바꾸고 비즈니스 함수를 부른 뒤 `to_api()`로 돌려준다. 규칙은 두지 않는다.
"""

import json
import logging
import time
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from aws_lambda_powertools.event_handler.exceptions import NotFoundError
from pydantic import Field, ValidationError

from ..core import clock
from ..core.alternatives import find_busan_alternatives
from ..core.companies import list_busan_companies
from ..core.compare import compare_postings
from ..core.policies import get_policy, match_policies
from ..core.posting_detail import get_posting
from ..core.preferences import get_preferences, set_preferences
from ..core.public_postings import list_public_postings
from ..core.ranking import search_postings
from ..core.saved import add_target_posting, list_saved, remove_saved
from ..deps import Deps
from ..enrich.ask import ask_policies, ask_policy, ask_posting
from ..enrich.explain import explain_posting
from ..models.api import AskRequest, DemoClockRequest, PreferencesUpdate, SaveRequest, TrackRequest
from ..models.base import OppModel
from ..models.enums import CheonggeulType, LeaveReason, PolicyStage, Sort, TrackEvent
from ..models.errors import OppError, invalid_input
from ..notify.notifier import advance_demo_clock, check_new_opportunities, mark_read
from ..notify.scheduler import subscribe_policy_alert
from . import errors

PREFIX = "/api/v1/opportunities"
PUBLIC_PATHS = {f"{PREFIX}/public/postings"}  # 로그인 없이 부르는 경로 (B-D10). API Gateway에서도 공개 경로다
CLIENT_EVENTS = {TrackEvent.ALT_CLICKED, TrackEvent.COMPARE_OPENED, TrackEvent.COST_TOGGLE_ON,
                 TrackEvent.BUSAN_FIRST_OFF, TrackEvent.POLICY_LINK_CLICKED}  # 서버가 남기는 이벤트는 받지 않는다

logger = logging.getLogger("opportunity.api")


def _dumps(body: Any) -> str:
    return json.dumps(body, ensure_ascii=False, separators=(",", ":"))


app = APIGatewayHttpResolver(serializer=_dumps)


# ---------------------------------------------------------------- 쿼리 모델 (카멜 표기)
class FeedQuery(OppModel):
    region: str = "ALL"
    sort: Sort | None = None
    job_codes: str | None = None  # 쉼표로 구분
    keyword: str | None = None
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1)
    regional_talent: bool | None = None  # true면 지역인재 전형이 있을 수 있는 공고만
    sector: str | None = None  # ALL·PUBLIC(공기업: 공공기관·지방공공기관)·PRIVATE(사기업) (B-D10)


class PublicPostingsQuery(OppModel):
    keyword: str | None = Field(default=None, max_length=50)
    region: str = "ALL"
    sector: str | None = None      # ALL·PUBLIC(공기업: 공공기관·지방공공기관)·PRIVATE(사기업)
    org_type: str | None = None    # ALL·PUBLIC_INSTITUTION·LOCAL_PUBLIC·PRIVATE
    career: str | None = None      # ALL·NEW·EXPERIENCED (신입·경력 무관 공고는 둘 다에 보인다)
    employment: str | None = None  # ALL·FULL_TIME·CONTRACT·PART_TIME·INTERN
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1)


class AlternativesQuery(OppModel):
    leave_reason: LeaveReason | None = None
    limit: int | None = Field(default=None, ge=1)


class CompareQuery(OppModel):
    base_job_posting_id: str
    alt_job_posting_id: str
    family_housing: bool = False


class PoliciesQuery(OppModel):
    stage: PolicyStage | None = None


class CompaniesQuery(OppModel):
    category: CheonggeulType | None = None
    limit: int | None = Field(default=None, ge=1, le=50)


class NotificationsQuery(OppModel):
    cursor: str | None = None
    limit: int | None = Field(default=None, ge=1)


# ---------------------------------------------------------------- 요청 도우미
def _deps() -> Deps:
    return app.context["deps"]


def _user_id() -> str:
    """토큰의 sub. 공개 경로로 들어온 요청에는 없으므로, 사용자 경로에서 비어 있으면 401로 막는다."""
    user_id = app.context.get("user_id")
    if not user_id:
        raise OppError(401, "UNAUTHORIZED", "로그인이 필요해요.")
    return user_id


def _request_id() -> str:
    try:
        return app.current_event.request_context.request_id or errors.new_request_id()
    except (AttributeError, KeyError, TypeError):
        return errors.new_request_id()


def _query(model: type[OppModel]):
    return model.model_validate(app.current_event.query_string_parameters or {})


def _body(model: type[OppModel]):
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


def _drop_none(**kwargs) -> dict:
    return {k: v for k, v in kwargs.items() if v is not None}


# ---------------------------------------------------------------- 공고
@app.get(f"{PREFIX}/public/postings")
def rest_public_postings():
    """로그인 없이 보는 공고 목록 (B-D10). 사용자 ID를 읽지 않는다."""
    q = _query(PublicPostingsQuery)
    return list_public_postings(_deps(), **_drop_none(keyword=q.keyword, region=q.region, sector=q.sector,
                                                      org_type=q.org_type,
                                                      career=q.career, employment=q.employment, cursor=q.cursor,
                                                      limit=q.limit)).to_api()


@app.get(f"{PREFIX}/postings")
def rest_search_postings():
    q = _query(FeedQuery)
    job_codes = [c.strip() for c in q.job_codes.split(",") if c.strip()] if q.job_codes else None
    return search_postings(_deps(), _user_id(), **_drop_none(region=q.region, sort=q.sort, job_codes=job_codes,
                                                             keyword=q.keyword, cursor=q.cursor,
                                                             limit=q.limit, regional_talent=q.regional_talent,
                                                             sector=q.sector)).to_api()


@app.get(f"{PREFIX}/postings/<job_posting_id>")
def rest_get_posting(job_posting_id: str):
    return get_posting(_deps(), _user_id(), _id(job_posting_id, "jobPostingId")).to_api()


@app.get(f"{PREFIX}/postings/<job_posting_id>/explanation")
def rest_explain_posting(job_posting_id: str):
    return explain_posting(_deps(), _user_id(), _id(job_posting_id, "jobPostingId")).to_api()


@app.post(f"{PREFIX}/postings/<job_posting_id>/ask")
def rest_ask_posting(job_posting_id: str):
    request = _body(AskRequest)
    return ask_posting(_deps(), _user_id(), _id(job_posting_id, "jobPostingId"), request.question).to_api()


@app.get(f"{PREFIX}/postings/<job_posting_id>/alternatives")
def rest_alternatives(job_posting_id: str):
    q = _query(AlternativesQuery)
    return find_busan_alternatives(_deps(), _user_id(), _id(job_posting_id, "jobPostingId"),
                                   **_drop_none(leave_reason=q.leave_reason, limit=q.limit)).to_api()


@app.get(f"{PREFIX}/compare")
def rest_compare():
    q = _query(CompareQuery)
    return compare_postings(_deps(), _user_id(), _id(q.base_job_posting_id, "baseJobPostingId"),
                            _id(q.alt_job_posting_id, "altJobPostingId"),
                            family_housing=q.family_housing).to_api()


# ---------------------------------------------------------------- 정책
@app.get(f"{PREFIX}/companies")
def rest_list_companies():
    """부산 기업 둘러보기. 청끌기업을 회사 정보로만 보여 준다 (DECISIONS.md B-D01)."""
    q = _query(CompaniesQuery)
    return list_busan_companies(_deps(), _user_id(), category=q.category, limit=q.limit).to_api()


@app.get(f"{PREFIX}/policies")
def rest_match_policies():
    q = _query(PoliciesQuery)
    return match_policies(_deps(), _user_id(), stage=q.stage).to_api()


@app.post(f"{PREFIX}/policies/ask")
def rest_ask_policies():
    return ask_policies(_deps(), _user_id(), _body(AskRequest).question).to_api()


@app.post(f"{PREFIX}/policies/<policy_id>/ask")
def rest_ask_policy(policy_id: str):
    request = _body(AskRequest)
    return ask_policy(_deps(), _user_id(), _id(policy_id, "policyId"), request.question).to_api()


@app.get(f"{PREFIX}/policies/<policy_id>")
def rest_get_policy(policy_id: str):
    return get_policy(_deps(), _user_id(), _id(policy_id, "policyId")).to_api()


@app.post(f"{PREFIX}/policies/<policy_id>/alerts")
def rest_subscribe_policy_alert(policy_id: str):
    result = subscribe_policy_alert(_deps(), _user_id(), _id(policy_id, "policyId"),
                                    idempotency_key=_header("Idempotency-Key"))
    return _json(201 if result.created else 200, result.to_api())


# ---------------------------------------------------------------- 설정
@app.get(f"{PREFIX}/me/preferences")
def rest_get_preferences():
    return get_preferences(_deps(), _user_id()).to_api()


@app.put(f"{PREFIX}/me/preferences")
def rest_set_preferences():
    return set_preferences(_deps(), _user_id(), _body(PreferencesUpdate)).to_api()


# ---------------------------------------------------------------- 저장
@app.get(f"{PREFIX}/saved")
def rest_list_saved():
    return list_saved(_deps(), _user_id()).to_api()


@app.post(f"{PREFIX}/saved")
def rest_add_saved():
    result = add_target_posting(_deps(), _user_id(), _body(SaveRequest), idempotency_key=_header("Idempotency-Key"))
    return _json(201 if result.created else 200, result.to_api())


@app.delete(f"{PREFIX}/saved/<job_posting_id>")
def rest_remove_saved(job_posting_id: str):
    return remove_saved(_deps(), _user_id(), _id(job_posting_id, "jobPostingId")).to_api()


# ---------------------------------------------------------------- 알림
@app.get(f"{PREFIX}/notifications")
def rest_notifications():
    q = _query(NotificationsQuery)
    return check_new_opportunities(_deps(), _user_id(), **_drop_none(cursor=q.cursor, limit=q.limit)).to_api()


@app.post(f"{PREFIX}/notifications/<notification_id>/read")
def rest_mark_read(notification_id: str):
    notification_id = _id(notification_id, "notificationId")
    if not mark_read(_deps(), _user_id(), notification_id):
        raise OppError(404, "NOTIFICATION_NOT_FOUND", "알림을 찾을 수 없어요.", False,
                       {"notificationId": notification_id})
    return {"notificationId": notification_id, "read": True}


# ---------------------------------------------------------------- 화면 이벤트·데모
@app.post(f"{PREFIX}/track")
def rest_track():
    request = _body(TrackRequest)
    if request.event not in CLIENT_EVENTS:
        raise invalid_input("화면에서 보낼 수 없는 이벤트예요.", field="event")
    # 지표에는 사용자 ID를 넣지 않는다
    _deps().events.emit(request.event, **_drop_none(jobPostingId=request.job_posting_id,
                                                    policyId=request.policy_id))
    return {"recorded": True}


@app.post(f"{PREFIX}/admin/demo-clock")
def rest_demo_clock():
    deps, user_id = _deps(), _user_id()
    profile = deps.users.get_basic_profile(user_id)
    if profile is None or not profile.is_demo:
        # 데모 계정이 아니면 경로가 있다는 것도 알리지 않는다 (docs/api.md §5: 403 대신 404)
        raise OppError(404, "NOT_FOUND", "찾을 수 없는 경로예요.")
    request = _body(DemoClockRequest)
    try:
        as_of = clock.iso(clock.parse_as_of(request.as_of))
    except ValueError:
        raise invalid_input("asOf는 YYYY-MM-DD나 ISO 8601 시각이어야 해요.", field="asOf") from None
    return advance_demo_clock(deps, user_id, as_of).to_api()


# ---------------------------------------------------------------- 오류 변환
@app.exception_handler(OppError)
def _on_opp_error(error: OppError):
    return _json(*errors.from_opp_error(error, _request_id()))


@app.exception_handler(ValidationError)
def _on_validation_error(error: ValidationError):
    return _json(*errors.from_validation_error(error, _request_id()))


@app.exception_handler(Exception)
def _on_unexpected(error: Exception):
    logger.error(json.dumps({"requestId": _request_id(), "errorType": type(error).__name__}))
    return _json(*errors.from_unexpected(error, _request_id()))


@app.not_found
def _on_not_found(error: NotFoundError):
    return _json(*errors.error_body(404, "NOT_FOUND", "찾을 수 없는 경로예요.", _request_id()))


# ---------------------------------------------------------------- 입구
def handle_public(event: dict, deps: Deps, context: Any = None) -> dict:
    """토큰 없이 들어온 요청의 입구. 공개 경로(`PUBLIC_PATHS`)만 받고 나머지는 401이다."""
    path = (event.get("rawPath") or "").rstrip("/")
    if path not in PUBLIC_PATHS:
        request_id = (event.get("requestContext") or {}).get("requestId") or errors.new_request_id()
        status, body = errors.from_opp_error(OppError(401, "UNAUTHORIZED", "로그인이 필요해요."), request_id)
        return {"statusCode": status, "headers": {"Content-Type": "application/json"}, "body": _dumps(body)}
    return handle(event, deps, None, context)


def handle(event: dict, deps: Deps, user_id: str | None, context: Any = None) -> dict:
    """백엔드 Lambda가 부르는 입구. user_id는 토큰의 sub이고, 요청 안의 userId는 보지 않는다.
    공개 경로는 `handle_public`이 user_id 없이 부른다. 그때 사용자 경로는 `_user_id()`가 401로 막는다."""
    started = time.perf_counter()
    app.append_context(deps=deps, user_id=user_id)
    response = app.resolve(event, context)
    http = (event.get("requestContext") or {}).get("http") or {}
    # 로그에는 requestId, 경로, 처리 시간, 오류 코드만 남긴다
    logger.info(json.dumps({
        "requestId": (event.get("requestContext") or {}).get("requestId"),
        "method": http.get("method"),
        "path": event.get("rawPath"),
        "status": response.get("statusCode"),
        "durationMs": round((time.perf_counter() - started) * 1000, 1),
        "errorCode": errors.error_code_of(response.get("body")),
    }, ensure_ascii=False))
    return response
