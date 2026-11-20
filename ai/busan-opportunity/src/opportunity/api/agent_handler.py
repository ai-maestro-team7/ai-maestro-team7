"""Action Group `BusanOpportunity` 입구 (개발계획서2 §5.9).

REST와 같은 비즈니스 함수를 부르고 응답만 줄인다: 공고는 최대 `agent.maxPostings`개, 사실 목록 위주, 긴 본문은 뺀다.
userId는 `sessionAttributes.userId`에서만 읽는다 (A 백엔드가 InvokeAgent 때 넣는다). 스키마에 userId 파라미터는
없고, 요청 파라미터에 userId가 섞여 와도 쓰지 않는다 (T-20).
저장 경로 `POST /agent/saved`는 P1이라 아직 없다.

스키마 다시 만들기: `python -m opportunity.api.agent_handler` → `api/schema.json`
"""

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from aws_lambda_powertools.event_handler import BedrockAgentResolver, Response
from aws_lambda_powertools.event_handler.openapi.exceptions import RequestValidationError
from aws_lambda_powertools.event_handler.openapi.params import Path as PathParam
from aws_lambda_powertools.event_handler.openapi.params import Query
from pydantic import Field, ValidationError

from ..config import get_config
from ..core import clock
from ..core.alternatives import find_busan_alternatives
from ..core.compare import compare_postings
from ..core.copy_rules import MATCH_LEVEL_LABEL, MATCH_NOT_PROBABILITY, deadline_label, salary_label
from ..core.policies import match_policies
from ..core.posting_detail import get_regional_talent
from ..core.ranking import search_postings
from ..deps import Deps
from ..models.api import (
    AlternativeItem,
    CompareRow,
    CostAdjusted,
    PolicyCard,
    PolicyTotals,
    PostingCard,
    RegionalTalentResponse,
)
from ..models.base import OppModel
from ..models.enums import PolicyStage
from ..models.errors import OppError
from ..models.posting import Badge
from . import errors

SCHEMA_PATH = Path(__file__).with_name("schema.json")
SCHEMA_TITLE = "BusanOpportunity"
SCHEMA_VERSION = "1.0.0"

agent = BedrockAgentResolver()
MAX_POSTINGS_DOC = get_config().agent.max_postings  # 스키마 설명용. 실제 상한은 요청마다 deps.config에서 읽는다


# ---------------------------------------------------------------- 줄인 응답 모델
class AgentPosting(OppModel):
    job_posting_id: str
    title: str
    organization: str
    work_region: str
    is_busan: bool
    is_capital_area: bool
    closes_at: str
    deadline: str | None = None  # "마감 D-9", "상시 채용"
    salary: str                  # "연 3,400~3,800만 원", "공고에 없음"
    match_level: str             # "잘 맞아요" 같은 3단계 말. 숫자 점수는 주지 않는다
    eligibility: str | None = None
    badges: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    busan_alternatives_count: int | None = None
    is_sample: bool = False


class AgentFeed(OppModel):
    items: list[AgentPosting] = Field(default_factory=list)
    ranking_basis: str
    notice: str = MATCH_NOT_PROBABILITY
    empty_message: str | None = None
    data_as_of: str | None = None
    stale: bool = False


class AgentAlternative(OppModel):
    job_posting_id: str
    title: str
    organization: str
    work_region: str
    closes_at: str
    deadline: str | None = None
    match_level: str
    why_shown: str
    badges: list[str] = Field(default_factory=list)
    facts: list[str] = Field(default_factory=list)
    is_sample: bool = False


class AgentAlternatives(OppModel):
    base_job_posting_id: str
    items: list[AgentAlternative] = Field(default_factory=list)
    expanded: bool = False
    no_alternative: bool = False
    reason: str | None = None
    suggest_compare: bool = True
    data_as_of: str | None = None


class AgentCompare(OppModel):
    base: str
    alt: str
    rows: list[CompareRow] = Field(default_factory=list)
    cost_adjusted: CostAdjusted
    suggest_more: bool = True
    data_as_of: str | None = None


class AgentPolicy(OppModel):
    policy_id: str
    title: str
    bucket: str
    status: str
    reasons: list[str] = Field(default_factory=list)
    manual_checks: list[str] = Field(default_factory=list)
    benefit: str | None = None
    selection: str | None = None
    apply_start: str | None = None
    apply_end: str | None = None
    expected: str | None = None
    source: str
    as_of: str | None = None
    url: str | None = None


class AgentPolicies(OppModel):
    items: list[AgentPolicy] = Field(default_factory=list)
    totals: PolicyTotals
    data_as_of: str | None = None


# ---------------------------------------------------------------- 변환
def _badges(badges: list[Badge]) -> list[str]:
    """출처·기준일이 있는 배지만 "이름 (출처, 기준일)"로 (T-08)."""
    return [f"{b.label} ({b.source}, {b.as_of})" for b in badges if b.source and b.as_of]


def _deadline(closes_at: str, as_of) -> str | None:
    return deadline_label(clock.d_day(closes_at, as_of))


def _posting(card: PostingCard, as_of) -> AgentPosting:
    return AgentPosting(
        job_posting_id=card.job_posting_id, title=card.title, organization=card.organization,
        work_region=card.work_region.label, is_busan=card.is_busan, is_capital_area=card.is_capital_area,
        closes_at=card.closes_at, deadline=_deadline(card.closes_at, as_of),
        salary=salary_label(card.salary.disclosed, card.salary.min, card.salary.max),
        match_level=MATCH_LEVEL_LABEL[card.match_level],
        eligibility=str(card.eligibility.status) if card.eligibility else None,
        badges=_badges(card.badges), facts=card.facts, busan_alternatives_count=card.busan_alternatives_count,
        is_sample=card.is_sample)


def _alternative(item: AlternativeItem, as_of) -> AgentAlternative:
    return AgentAlternative(
        job_posting_id=item.job_posting_id, title=item.title, organization=item.organization,
        work_region=item.work_region.label, closes_at=item.closes_at, deadline=_deadline(item.closes_at, as_of),
        match_level=MATCH_LEVEL_LABEL[item.match_level], why_shown=item.why_shown, badges=_badges(item.badges),
        facts=item.facts, is_sample=item.is_sample)


def _policy(card: PolicyCard) -> AgentPolicy:
    app = card.application
    return AgentPolicy(
        policy_id=card.policy_id, title=card.title, bucket=str(card.bucket), status=str(card.eligibility.status),
        reasons=card.eligibility.reasons, manual_checks=card.eligibility.manual_checks,
        benefit=card.benefit.text if card.benefit else None,
        selection=str(app.selection) if app.selection else None, apply_start=app.apply_start,
        apply_end=app.apply_end, expected=app.expected, source=card.source, as_of=card.as_of, url=card.url)


# ---------------------------------------------------------------- 요청 도우미
def _deps() -> Deps:
    return agent.context["deps"]


def _user_id() -> str:
    """sessionAttributes.userId만 쓴다. 파라미터의 userId는 보지 않는다 (T-20)."""
    user_id = (agent.current_event.session_attributes or {}).get("userId")
    if not user_id:
        raise OppError(401, "UNAUTHORIZED", "사용자 정보가 없어요.")
    return user_id


def _as_of(deps: Deps, user_id: str):
    return clock.resolve_as_of(None, deps.users.get_prefs(user_id).demo_as_of)


def _max_postings() -> int:
    return _deps().config.agent.max_postings


# ---------------------------------------------------------------- 경로
@agent.get("/agent/postings",
           description="사용자에게 맞는 채용공고를 찾는다. 사용자가 일자리·채용공고를 물을 때 쓴다. "
                       f"비슷하게 맞으면 부산 근무 공고를 먼저 돌려준다. 공고는 최대 {MAX_POSTINGS_DOC}개이고 "
                       "적합도는 3단계 말로만 준다.")
def agent_search_postings(
    keyword: Annotated[str | None, Query(description="찾을 직무·회사 낱말. 없으면 희망 직무로 찾는다")] = None,
    region: Annotated[Literal["ALL", "BUSAN"], Query(description="ALL(전국) 또는 BUSAN(부산 근무만)")] = "ALL",
    limit: Annotated[int | None, Query(description=f"돌려받을 공고 수. 최대 {MAX_POSTINGS_DOC}", ge=1)] = None,
) -> AgentFeed:
    deps, user_id = _deps(), _user_id()
    size = min(limit or _max_postings(), _max_postings())
    feed = search_postings(deps, user_id, region=region, keyword=keyword, limit=size)
    as_of = _as_of(deps, user_id)
    return AgentFeed(items=[_posting(card, as_of) for card in feed.items[:size]], ranking_basis=feed.ranking.basis,
                     empty_message=feed.empty_message, data_as_of=feed.data_as_of, stale=feed.stale)


@agent.get("/agent/postings/<jobPostingId>/alternatives",
           description="수도권 공고와 하는 일이 비슷한 부산 공고를 찾는다. 사용자가 수도권 공고를 말하거나 "
                       "비교하려 할 때 쓴다. 대안이 없으면 noAlternative=true다. suggestCompare=false면 비교를 권하지 않는다.")
def agent_alternatives(
    jobPostingId: Annotated[str, PathParam(description="기준 공고 ID (예: wk24-…, alio-…)")],
) -> AgentAlternatives:
    deps, user_id = _deps(), _user_id()
    result = find_busan_alternatives(deps, user_id, jobPostingId, limit=_max_postings())
    as_of = _as_of(deps, user_id)
    return AgentAlternatives(
        base_job_posting_id=result.base_job_posting_id,
        items=[_alternative(item, as_of) for item in result.alternatives[:_max_postings()]],
        expanded=result.expanded, no_alternative=result.no_alternative, reason=result.reason,
        suggest_compare=result.suggest_compare, data_as_of=result.data_as_of)


@agent.get("/agent/compare",
           description="두 공고를 급여·주거비·통근·지역 정책·지역인재 기준으로 나란히 비교한다. 사용자가 두 공고를 "
                       "견주어 보고 싶어 할 때 쓴다. 값만 나란히 주고 어느 쪽이 낫다고 판정하지 않는다.")
def agent_compare(
    baseJobPostingId: Annotated[str, Query(description="기준 공고 ID (보통 수도권 공고)")],
    altJobPostingId: Annotated[str, Query(description="비교할 공고 ID (보통 부산 공고)")],
) -> AgentCompare:
    result = compare_postings(_deps(), _user_id(), baseJobPostingId, altJobPostingId)
    return AgentCompare(base=result.base.label, alt=result.alt.label, rows=result.rows,
                        cost_adjusted=result.cost_adjusted, suggest_more=result.suggest_more,
                        data_as_of=result.data_as_of)


@agent.get("/agent/policies",
           description="사용자가 받을 수 있는 청년 정책과 판정 이유를 단계별로 돌려준다. 지원금·주거·자산 정책을 물을 때 "
                       "쓴다. guaranteedIfEligible은 자격이 맞으면 받는 지원, selectiveMax는 선정되면 최대 금액이다.")
def agent_policies(
    stage: Annotated[PolicyStage | None, Query(description="PREPARE(취업 준비), EMPLOYED(취업 후), SETTLE(정착)")] = None,
) -> AgentPolicies:
    wallet = match_policies(_deps(), _user_id(), stage=stage)
    items = [_policy(card) for bucket in wallet.buckets.values() for card in bucket]
    return AgentPolicies(items=items, totals=wallet.totals, data_as_of=wallet.data_as_of)


@agent.get("/agent/postings/<jobPostingId>/regional-talent",
           description="공공기관 공고의 지역인재 전형 해당 가능성을 돌려준다. 사용자가 이전 공공기관·공기업 공고의 "
                       "지역인재 전형을 물을 때 쓴다. 결과는 '대상일 수 있어요'까지만이고 공고문 확인이 필요하다.")
def agent_regional_talent(
    jobPostingId: Annotated[str, PathParam(description="공고 ID")],
) -> RegionalTalentResponse:
    return get_regional_talent(_deps(), _user_id(), jobPostingId)


# ---------------------------------------------------------------- 오류 변환
def _json(status: int, body: dict) -> Response:
    return Response(status_code=status, content_type="application/json", body=body)


@agent.exception_handler(OppError)
def _on_opp_error(error: OppError):
    return _json(*errors.from_opp_error(error, errors.new_request_id()))


@agent.exception_handler(RequestValidationError)
def _on_request_validation(error: RequestValidationError):
    fields = sorted({".".join(str(p) for p in e.get("loc", ())) for e in error.errors()})
    return _json(*errors.error_body(400, "INVALID_INPUT", "입력 형식이 올바르지 않아요.", errors.new_request_id(),
                                    details={"fields": fields}))


@agent.exception_handler(ValidationError)
def _on_validation_error(error: ValidationError):
    return _json(*errors.from_validation_error(error, errors.new_request_id()))


@agent.exception_handler(Exception)
def _on_unexpected(error: Exception):
    return _json(*errors.from_unexpected(error, errors.new_request_id()))


# ---------------------------------------------------------------- 입구·스키마
def handle(event: dict, deps: Deps, context: Any = None) -> dict:
    """Action Group Lambda가 부르는 입구. userId는 event의 sessionAttributes에서만 읽는다."""
    agent.append_context(deps=deps)
    return agent.resolve(event, context)


def build_schema() -> dict:
    """Agent에 올릴 OpenAPI 3.0 스키마."""
    return json.loads(agent.get_openapi_json_schema(title=SCHEMA_TITLE, version=SCHEMA_VERSION,
                                                    description="부산 채용공고·청년정책 조회 도구 (B 파트)"))


def write_schema(path: Path = SCHEMA_PATH) -> None:
    path.write_text(json.dumps(build_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_schema()
