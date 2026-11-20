"""질문하기 (RAG). 정책·공고 원문을 근거로 답을 만든다.

검색은 Knowledge Base의 Retrieve(`deps.retriever`)로 하고, 답은 `deps.llm`으로 만든다. RetrieveAndGenerate는 쓰지 않는다.
자격 판정은 규칙 엔진(`core.policies.judge_policy`)이 하고 LLM은 그 결과를 전하기만 한다.
신청 기간도 코드가 기준일(as_of)로 비교해 "지남/진행 중/상시/시작 전" 같은 상태로 넘긴다. 같은 정책의 지난 회차는
최신 회차 하나만 남긴다 (`latest_rounds`).
LLM 답은 코드로 검증한다: JSON 형식, 인용이 넘긴 문서에 글자 그대로 있는지, 답의 숫자가 문서·판정 이유에 있는지,
금지 문구. 실패하면 한 번 다시 시도하고, 또 실패하면 answered=false로 돌려준다 (예외를 던지지 않는다).
질문 원문은 로그와 이벤트에 남기지 않는다.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from ..core import clock, copy_rules, regions
from ..core.context import load_context
from ..core.policies import _bucket, _timing, judge_policy
from ..deps import Deps
from ..models.api import AskResponse, AskSource, PolicyBrief, PolicyJudgement
from ..models.enums import PeriodType, PolicyEligibilityStatus
from ..models.errors import OppError, invalid_input, policy_not_found, posting_not_found
from ..models.policy import ALWAYS_APPLY_END, Policy
from ..models.posting import ROLLING_CLOSES_AT
from ..models.profile import BasicProfile
from . import prompts
from .extract import quote_in_source

# 검증에 실패하면 한 번만 다시 만든다. 처음 + 다시 = 2
MAX_ATTEMPTS = 2
EVENT = "ASK"
KIND_POLICIES, KIND_POLICY, KIND_POSTING = "POLICIES", "POLICY", "POSTING"
SOURCE_POLICY, SOURCE_POSTING = "POLICY", "POSTING"

_DATE8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$")


# ---------------------------------------------------------------- LLM 출력 계약
class _Citation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(validation_alias=AliasChoices("policyId", "jobPostingId", "id"))
    quote: str


class AskOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    answer: str = ""
    citations: list[_Citation] = Field(default_factory=list)
    not_found: bool = Field(default=False, alias="notFound")


@dataclass
class _Doc:
    doc_id: str
    title: str
    text: str           # LLM에 넘긴 글 (max_doc_chars까지). 인용은 이 글과 대조한다
    url: str | None
    as_of: str | None


@dataclass
class _Checked:
    answer: str
    sources: list[AskSource]


# ---------------------------------------------------------------- 입력
def clean_question(deps: Deps, question: str | None) -> str:
    text = (question or "").strip()
    if not text:
        raise invalid_input("질문을 입력해 주세요.", field="question")
    if len(text) > deps.config.ask.max_question_chars:
        raise invalid_input(f"질문은 {deps.config.ask.max_question_chars}자까지 쓸 수 있어요.", field="question")
    return text


# ---------------------------------------------------------------- 검색 필터
def _equals(key: str, value: str) -> dict:
    return {"equals": {"key": key, "value": value}}


def any_of(conditions: list[dict]) -> dict:
    """조건이 1개면 그 조건만. Bedrock은 원소 1개짜리 orAll을 거절한다."""
    return conditions[0] if len(conditions) == 1 else {"orAll": conditions}


def all_of(conditions: list[dict]) -> dict:
    return conditions[0] if len(conditions) == 1 else {"andAll": conditions}


def mentioned_sidos(question: str) -> list[str]:
    """질문에 나온 시·도 코드 (SIDO_NAMES 순서)."""
    return [code for code, name in regions.SIDO_NAMES.items() if name in question]


def policy_filter(profile: BasicProfile, question: str) -> dict | None:
    """거주 시·도 + 전국 + 질문에 나온 시·도. 구 단위 정책은 사용자 구와 같을 때만. 거주지가 없으면 None."""
    if not profile.residence_sido:
        return None
    keys = list(dict.fromkeys([profile.residence_sido, regions.NATIONAL, *mentioned_sidos(question)]))
    gu = [{"notEquals": {"key": "scope", "value": "SIGUNGU"}}]
    if profile.residence_sigungu:
        gu.append(_equals("sigungu", profile.residence_sigungu))
    return all_of([any_of([_equals("regionKey", k) for k in keys]), any_of(gu)])


# ---------------------------------------------------------------- 검증
def _norm_number(n: str) -> str:
    return n if "." in n else (n.lstrip("0") or "0")


def allowed_numbers(texts: list[str]) -> set[str]:
    """문서·판정 이유의 숫자. 앞자리 0은 떼고, YYYYMMDD는 연·월·일로도 허용한다 (2026년 3월 2일)."""
    allowed: set[str] = set()
    for text in texts:
        for n in copy_rules.numbers_in(text):
            allowed.add(_norm_number(n))
            m = _DATE8.match(n)
            if m:
                allowed.update(_norm_number(part) for part in m.groups())
    return allowed


def _parse(reply: str) -> AskOutput | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(reply[start:end + 1])
        return AskOutput.model_validate(data) if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValidationError, TypeError):
        return None


def check_answer(out: AskOutput, docs: list[_Doc], extra_texts: list[str], kind: str) -> _Checked | None:
    """통과하면 답과 근거, 아니면 None. 문서에 없는 인용은 그것만 버리고, 하나도 안 남으면 실패다."""
    answer = out.answer.strip()
    if not answer or copy_rules.find_forbidden(answer):
        return None
    by_id = {d.doc_id: d for d in docs}
    allowed = allowed_numbers([d.text for d in docs] + [d.title for d in docs] + extra_texts)
    if {_norm_number(n) for n in copy_rules.numbers_in(answer)} - allowed:
        return None
    sources: list[AskSource] = []
    seen: set[tuple[str, str]] = set()
    for c in out.citations:
        doc = by_id.get(c.id)
        quote = c.quote.strip()
        if doc is None or not quote_in_source(quote, doc.text) or (doc.doc_id, quote) in seen:
            continue
        seen.add((doc.doc_id, quote))
        sources.append(AskSource(kind=kind, id=doc.doc_id, title=doc.title, quote=quote, url=doc.url,
                                 as_of=doc.as_of))
    return _Checked(answer, sources) if sources else None


# ---------------------------------------------------------------- 공용 흐름
def _response(deps: Deps, event_kind: str, question: str, *, answered: bool, **fields) -> AskResponse:
    deps.events.emit(EVENT, kind=event_kind, answered=answered)  # 질문 원문은 넣지 않는다
    return AskResponse(question=question, answered=answered, data_as_of=deps.catalog.data_as_of(), **fields)


def _generate(deps: Deps, question: str, docs: list[_Doc], *, tag: str, id_key: str, source_kind: str,
              judgements: list[tuple[str, str, list[str]]] | None = None,
              periods: dict[str, str] | None = None) -> tuple[str, _Checked | None]:
    """("OK"|"NOT_FOUND"|"FAILED", 검증된 답). periods는 {정책 id: 신청 기간 줄}이다."""
    system = prompts.ask_system(tag, id_key)
    user = prompts.ask_user(question, tag, [(d.doc_id, d.title, d.text) for d in docs], judgements, periods=periods)
    # 판정 이유와 신청 기간 줄의 숫자(날짜)도 답에 써도 되는 숫자다
    extra = [reason for _, _, reasons in (judgements or []) for reason in reasons] + list((periods or {}).values())
    for _ in range(MAX_ATTEMPTS):
        try:
            reply = deps.llm.invoke(system, user, max_tokens=deps.config.ask.max_tokens)
        except Exception:  # noqa: BLE001, S112 — 모델 오류도 실패 한 번으로 센다. 정책 목록은 그대로 준다
            continue
        out = _parse(reply or "")
        if out is None:
            continue
        if out.not_found:
            return "NOT_FOUND", None
        checked = check_answer(out, docs, extra, source_kind)
        if checked is not None:
            return "OK", checked
    return "FAILED", None


def _finish(deps: Deps, event_kind: str, question: str, status: str, checked: _Checked | None,
            **fields) -> AskResponse:
    if status == "OK" and checked is not None:
        return _response(deps, event_kind, question, answered=True, answer=checked.answer, sources=checked.sources,
                         **fields)
    notice = copy_rules.ASK_NOT_FOUND if status == "NOT_FOUND" else copy_rules.ASK_UNAVAILABLE
    return _response(deps, event_kind, question, answered=False, notice=notice, **fields)


def _cut(deps: Deps, text: str) -> str:
    return text[:deps.config.ask.max_doc_chars]


# ---------------------------------------------------------------- 신청 기간과 회차
APPLY_PAST, APPLY_OPEN, APPLY_ALWAYS, APPLY_MONTHLY = "PAST", "OPEN", "ALWAYS", "MONTHLY"
APPLY_UPCOMING, APPLY_TBD, APPLY_UNKNOWN = "UPCOMING", "TBD", "UNKNOWN"

# 회차를 가르는 이름 비교에서 뗄 것: 공백, 괄호 글자(안의 말은 남긴다), 연도(2025, 2025년, 2025년도)
_NAME_NOISE = re.compile(r"[\s()\[\]{}<>（）［］【】「」『』〈〉《》]")
_NAME_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)(?:년도|년)?")


def apply_status(policy: Policy, as_of: str | date | datetime) -> str:
    """신청 상태. 날짜 비교는 여기서만 한다 (`clock.day(as_of)`, 시작일·종료일 당일은 진행 중).

    상시(ALWAYS) → ALWAYS, 매월(MONTHLY) → MONTHLY. 그 밖에는 날짜로 본다:
    시작일 전이면 UPCOMING, 종료일이 지났으면 PAST, 그 사이면 OPEN.
    날짜가 하나도 없으면 TBD(다음 일정 미정)거나 UNKNOWN(FIXED인데 날짜 없음, 확인 필요)이다.
    """
    period = policy.application.period_type
    if period == PeriodType.ALWAYS:
        return APPLY_ALWAYS
    if period == PeriodType.MONTHLY:
        return APPLY_MONTHLY
    has_end = policy.apply_end != ALWAYS_APPLY_END
    if not policy.apply_start and not has_end:
        return APPLY_TBD if period == PeriodType.TBD else APPLY_UNKNOWN
    today = clock.day(as_of)
    if policy.apply_start and today < policy.apply_start:
        return APPLY_UPCOMING
    if has_end and policy.apply_end < today:
        return APPLY_PAST
    return APPLY_OPEN


def period_line(policy: Policy, as_of: str | date | datetime) -> str:
    """LLM에 사실로 넘기는 줄. 예: "신청 기간: 2026-08-10 ~ 2026-08-21 (지남)", "신청 기간: 상시"."""
    label = prompts.APPLY_STATUS_LABEL[apply_status(policy, as_of)]
    start = policy.apply_start or ""
    end = "" if policy.apply_end == ALWAYS_APPLY_END else policy.apply_end
    if not start and not end:
        return f"신청 기간: {label}"
    return f"신청 기간: {f'{start} ~ {end}'.strip()} ({label})"


def round_name(title: str) -> str:
    """회차 비교용 이름. 연도·괄호 글자·공백을 뗀다.
    "부산 청년 자산형성 지원(부산청년 기쁨두배통장)" → "부산청년자산형성지원부산청년기쁨두배통장"
    """
    return _NAME_NOISE.sub("", _NAME_YEAR.sub("", title))


def _regions(policy: Policy) -> set[tuple[str, str | None, str | None]]:
    return {(str(r.scope), r.sido, r.sigungu) for r in policy.regions}


def _dated_period(policy: Policy) -> tuple[str, str] | None:
    """날짜가 적힌 모집 기간 (시작, 끝). 상시·매월이거나 날짜가 없으면 None. 시작일이 없으면 끝날 하루로 본다."""
    if policy.application.period_type in (PeriodType.ALWAYS, PeriodType.MONTHLY):
        return None
    if policy.apply_end == ALWAYS_APPLY_END:
        return None
    return policy.apply_start or policy.apply_end, policy.apply_end


def same_policy_round(a: Policy, b: Policy) -> bool:
    """같은 정책의 다른 회차로 보는 규칙.

    1. 대상 지역(`Policy.regions`의 범위·시도·시군구)이 같아야 한다. 이름이 겹쳐도 부산진구 정책과 기장군 정책,
       서울 정책과 부산 정책은 다른 정책이다.
    2. 회차 비교용 이름(`round_name`)이 같으면 같은 정책이다.
    3. 이름이 같지 않고 한쪽이 다른 쪽을 포함하면, 둘 다 날짜가 적힌 모집 기간이 있고 두 기간이 겹치지 않을 때만
       같은 정책의 다른 회차로 본다. 예: "부산청년기쁨두배통장"(2025-07-01~07-31) ⊂
       "부산청년자산형성지원부산청년기쁨두배통장"(2026-08-10~08-21).
       기간이 겹치거나 한쪽이 상시·일정 미정이면 함께 운영되는 별개 사업일 수 있어 합치지 않는다.
       실제 데이터 예: "산림산업 창업지원"(일정 미정)과 "산림산업 창업지원_청년 산림인 성장지원"(2026-02)은 따로 둔다.
    """
    if _regions(a) != _regions(b):
        return False
    na, nb = round_name(a.title), round_name(b.title)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na not in nb and nb not in na:
        return False
    pa, pb = _dated_period(a), _dated_period(b)
    if pa is None or pb is None:
        return False
    return pa[1] < pb[0] or pb[1] < pa[0]


def _round_end(policy: Policy) -> str:
    """최신 회차를 고르는 키. 상시·매월은 가장 늦게, 날짜가 없는 일정 미정은 가장 이르게 본다
    (종료일을 모르는 회차가 날짜가 적힌 회차를 밀어내지 않게 한다)."""
    if policy.application.period_type in (PeriodType.ALWAYS, PeriodType.MONTHLY):
        return ALWAYS_APPLY_END
    if policy.apply_end == ALWAYS_APPLY_END and not policy.apply_start:
        return ""
    return policy.apply_end


def latest_rounds(items: list) -> list:
    """같은 정책의 회차가 여럿이면 신청 종료일이 가장 늦은 하나만 남긴다. items의 첫 값은 Policy여야 한다.

    - 받은 순서(검색 점수 순)로 묶음을 만든다. 앞서 나온 묶음의 정책 하나와라도 `same_policy_round`면 그 묶음에 넣는다.
    - 묶음마다 `_round_end`가 가장 늦은 것을 남긴다. 같으면 먼저 나온(점수가 높은) 것을 남긴다.
    - 남긴 것은 그 묶음에서 처음 나온 정책의 자리에 둔다. 묶음 안에서 가장 높은 검색 점수가 순서를 정한다.
    """
    groups: list[list] = []
    for item in items:
        group = next((g for g in groups if any(same_policy_round(item[0], other[0]) for other in g)), None)
        if group is None:
            groups.append([item])
        else:
            group.append(item)
    kept = []
    for group in groups:
        best = group[0]
        for item in group[1:]:
            if _round_end(item[0]) > _round_end(best[0]):
                best = item
        kept.append(best)
    return kept


def _order_key(policy: Policy, judgement: PolicyJudgement, as_of: datetime) -> tuple[bool, bool]:
    """신청 기간이 지난 정책은 진행 중·상시·시작 전 정책 뒤로, 그 안에서 NOT_ELIGIBLE은 뒤로 보낸다.
    숨기지 않는다. 안정 정렬이라 같은 칸 안에서는 검색 점수 순서가 그대로다."""
    return apply_status(policy, as_of) == APPLY_PAST, judgement.status == PolicyEligibilityStatus.NOT_ELIGIBLE


def _periods(picked: list[tuple[Policy, PolicyJudgement]], as_of: datetime) -> dict[str, str]:
    return {p.policy_id: period_line(p, as_of) for p, _ in picked}


# ---------------------------------------------------------------- 정책
def _brief(policy: Policy, judgement: PolicyJudgement, profile: BasicProfile, as_of: datetime) -> PolicyBrief:
    bucket = _bucket(policy, judgement, profile, _timing(policy, as_of))
    return PolicyBrief(policy_id=policy.policy_id, title=policy.title, bucket=bucket, status=judgement.status,
                       summary=policy.summary)


def _manual_checks(judgements: list[PolicyJudgement]) -> list[str]:
    return list(dict.fromkeys(check for j in judgements for check in j.manual_checks))


def _judgement_rows(picked: list[tuple[Policy, PolicyJudgement]]) -> list[tuple[str, str, list[str]]]:
    return [(p.policy_id, str(j.status), list(j.reasons)) for p, j in picked]


def _policy_doc(deps: Deps, policy: Policy, text: str) -> _Doc:
    return _Doc(policy.policy_id, policy.title, _cut(deps, text), policy.url, policy.as_of)


def policy_text(policy: Policy) -> str:
    """KB 문서를 못 가져왔을 때 catalog 값으로 만드는 글. 값이 없는 줄은 뺀다."""
    e = policy.eligibility
    low = e.age_min if e.age_min is not None else policy.age_min
    high = e.age_max if e.age_max is not None else policy.age_max
    period = None
    if policy.apply_start or policy.apply_end != ALWAYS_APPLY_END:
        period = f"{policy.apply_start or ''} ~ {'' if policy.apply_end == ALWAYS_APPLY_END else policy.apply_end}"
    rows = [
        ("요약", policy.summary),
        ("지원 내용", policy.benefit.text if policy.benefit and policy.benefit.text != policy.summary else None),
        ("지원 나이", f"만 {low if low is not None else '-'}세 ~ 만 {high if high is not None else '-'}세"
         if low is not None or high is not None else None),
        ("거주 조건", policy.residence_rule),
        ("소득 조건", e.income.text if e.income else policy.income_rule),
        ("신청 기간", period),
        ("다음 모집", policy.application.expected),
        ("직접 확인할 조건", " / ".join(e.manual_checks) if e.manual_checks else None),
        ("제출 서류", ", ".join(policy.checklist) if policy.checklist else None),
        ("중복 불가", ", ".join(policy.exclusive_with) if policy.exclusive_with else None),
    ]
    lines = [f"# {policy.title}", ""] + [f"{label}: {value}" for label, value in rows if value]
    return "\n".join(lines).strip()


def ask_policies(deps: Deps, user_id: str, question: str, *,
                 as_of: str | date | datetime | None = None) -> AskResponse:
    """정책 검색 RAG. 거주 시·도·전국(+질문에 나온 시·도) 정책을 검색해 규칙으로 판정하고 원문을 근거로 답한다.

    검색 점수 순서를 지키되 같은 정책의 지난 회차는 최신 회차 하나로 줄이고(`latest_rounds`), 신청 기간이 지난 정책과
    NOT_ELIGIBLE은 뒤로 보낸다(숨기지 않는다, `_order_key`). 부산 정책을 따로 올리지 않는다.
    catalog에 없거나 verified=false인 정책은 뺀다. retriever나 llm이 없으면 answered=false.
    """
    question = clean_question(deps, question)
    if deps.retriever is None or deps.llm is None:
        return _response(deps, KIND_POLICIES, question, answered=False, notice=copy_rules.ASK_UNAVAILABLE)
    cfg = deps.config.ask
    ctx = load_context(deps, user_id, as_of)
    hits = deps.retriever.retrieve(question, top_k=cfg.candidate_k, filter=policy_filter(ctx.profile, question))

    candidates: list[tuple[Policy, PolicyJudgement, str]] = []
    seen: set[str] = set()
    for hit in sorted(hits, key=lambda h: -h.score):  # 같은 점수는 받은 순서를 지킨다
        if hit.doc_id in seen:
            continue
        seen.add(hit.doc_id)
        policy = deps.catalog.get_policy(hit.doc_id)
        if policy is None or not policy.verified:
            continue
        judgement = judge_policy(policy, ctx.profile, ctx.prefs, as_of=ctx.as_of)
        candidates.append((policy, judgement, hit.text))
    candidates = latest_rounds(candidates)
    candidates.sort(key=lambda c: _order_key(c[0], c[1], ctx.as_of))
    picked = candidates[:cfg.top_k]
    if not picked:
        return _response(deps, KIND_POLICIES, question, answered=False, notice=copy_rules.ASK_NOT_FOUND)

    pairs = [(p, j) for p, j, _ in picked]
    fields = {"related_policies": [_brief(p, j, ctx.profile, ctx.as_of) for p, j in pairs],
              "manual_checks": _manual_checks([j for _, j in pairs])}
    docs = [_policy_doc(deps, p, text) for p, _, text in picked]
    status, checked = _generate(deps, question, docs, tag="policy", id_key="policyId", source_kind=SOURCE_POLICY,
                                judgements=_judgement_rows(pairs), periods=_periods(pairs, ctx.as_of))
    return _finish(deps, KIND_POLICIES, question, status, checked, **fields)


def _kb_text(deps: Deps, policy_id: str, question: str) -> str | None:
    """KB에서 그 정책 문서만 가져온다. 없거나 검색이 실패하면 None (catalog 글로 대신한다)."""
    if deps.retriever is None:
        return None
    try:
        hits = deps.retriever.retrieve(question, top_k=1, filter=_equals("policyId", policy_id))
    except OppError:
        return None
    return next((h.text for h in hits if h.doc_id == policy_id and h.text.strip()), None)


def ask_policy(deps: Deps, user_id: str, policy_id: str, question: str, *,
               as_of: str | date | datetime | None = None) -> AskResponse:
    """보고 있는 정책 한 건에 질문한다. 검색하지 않고 그 정책 문서만 쓴다. 없거나 verified=false면 POLICY_NOT_FOUND."""
    question = clean_question(deps, question)
    policy = deps.catalog.get_policy(policy_id)
    if policy is None or not policy.verified:
        raise policy_not_found(policy_id)
    ctx = load_context(deps, user_id, as_of)
    judgement = judge_policy(policy, ctx.profile, ctx.prefs, as_of=ctx.as_of)
    fields = {"related_policies": [_brief(policy, judgement, ctx.profile, ctx.as_of)],
              "manual_checks": _manual_checks([judgement])}
    if deps.llm is None:
        return _response(deps, KIND_POLICY, question, answered=False, notice=copy_rules.ASK_UNAVAILABLE, **fields)
    text = _kb_text(deps, policy_id, question) or policy_text(policy)
    status, checked = _generate(deps, question, [_policy_doc(deps, policy, text)], tag="policy", id_key="policyId",
                                source_kind=SOURCE_POLICY, judgements=_judgement_rows([(policy, judgement)]),
                                periods=_periods([(policy, judgement)], ctx.as_of))
    return _finish(deps, KIND_POLICY, question, status, checked, **fields)


# ---------------------------------------------------------------- 공고
def posting_text(snapshot) -> str:
    """스냅샷의 업무 설명·요건·전형으로 만든 글. 요건은 원문 문장(sourceQuote)이 있으면 그것을 쓴다."""
    closes = "상시 채용" if snapshot.rolling or snapshot.closes_at == ROLLING_CLOSES_AT else snapshot.closes_at
    lines = [f"# {snapshot.title}", "", f"기관: {snapshot.organization}", f"근무지: {snapshot.work_region.label}",
             f"마감: {closes}"]
    if snapshot.job_description:
        lines += ["", "## 하는 일", snapshot.job_description.strip()]
    for kind, title in (("REQUIRED_SKILL", "필수 요건"), ("PREFERRED_SKILL", "우대 사항")):
        reqs = [r for r in snapshot.requirements if str(r.kind) == kind]
        if reqs:
            lines += ["", f"## {title}"] + [f"- {r.source_quote or r.name}" for r in reqs]
    if snapshot.selection_steps:
        lines += ["", "## 전형", " → ".join(snapshot.selection_steps)]
    if snapshot.documents:
        lines += ["", "## 제출 서류", ", ".join(snapshot.documents)]
    return "\n".join(lines).strip()


def ask_posting(deps: Deps, user_id: str, job_posting_id: str, question: str, *,
                as_of: str | date | datetime | None = None) -> AskResponse:
    """보고 있는 공고 한 건에 질문한다. 스냅샷 글만 쓴다. 없으면 POSTING_NOT_FOUND."""
    question = clean_question(deps, question)
    latest = deps.catalog.get_latest(job_posting_id)
    snapshot = deps.catalog.get_snapshot(job_posting_id, latest.snapshot_id) if latest else None
    if snapshot is None:
        raise posting_not_found(job_posting_id)
    load_context(deps, user_id, as_of)  # 다른 질문 함수와 같이 사용자 문맥을 확인한다
    if deps.llm is None:
        return _response(deps, KIND_POSTING, question, answered=False, notice=copy_rules.ASK_UNAVAILABLE)
    doc = _Doc(job_posting_id, snapshot.title, _cut(deps, posting_text(snapshot)), snapshot.official_url,
               snapshot.checked_at)
    status, checked = _generate(deps, question, [doc], tag="posting", id_key="jobPostingId",
                                source_kind=SOURCE_POSTING)
    return _finish(deps, KIND_POSTING, question, status, checked)
