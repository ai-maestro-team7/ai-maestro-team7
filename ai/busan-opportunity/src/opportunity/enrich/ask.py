"""질문하기 (RAG). 정책·공고 원문을 근거로 답을 만든다.

검색은 Knowledge Base의 Retrieve(`deps.retriever`)로 하고, 답은 `deps.llm`으로 만든다. RetrieveAndGenerate는 쓰지 않는다.
자격 판정은 규칙 엔진(`core.policies.judge_policy`)이 하고 LLM은 그 결과를 전하기만 한다.
LLM 답은 코드로 검증한다: JSON 형식, 인용이 넘긴 문서에 글자 그대로 있는지, 답의 숫자가 문서·판정 이유에 있는지,
금지 문구. 실패하면 한 번 다시 시도하고, 또 실패하면 answered=false로 돌려준다 (예외를 던지지 않는다).
질문 원문은 로그와 이벤트에 남기지 않는다.
"""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError

from ..core import copy_rules, regions
from ..core.context import load_context
from ..core.policies import _bucket, _timing, judge_policy
from ..deps import Deps
from ..models.api import AskResponse, AskSource, PolicyBrief, PolicyJudgement
from ..models.enums import PolicyEligibilityStatus
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
              judgements: list[tuple[str, str, list[str]]] | None = None) -> tuple[str, _Checked | None]:
    """("OK"|"NOT_FOUND"|"FAILED", 검증된 답)."""
    system = prompts.ask_system(tag, id_key)
    user = prompts.ask_user(question, tag, [(d.doc_id, d.title, d.text) for d in docs], judgements)
    extra = [reason for _, _, reasons in (judgements or []) for reason in reasons]
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

    검색 점수 순서를 지키되 NOT_ELIGIBLE은 뒤로 보낸다(숨기지 않는다). 부산 정책을 따로 올리지 않는다.
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
    candidates.sort(key=lambda c: c[1].status == PolicyEligibilityStatus.NOT_ELIGIBLE)
    picked = candidates[:cfg.top_k]
    if not picked:
        return _response(deps, KIND_POLICIES, question, answered=False, notice=copy_rules.ASK_NOT_FOUND)

    pairs = [(p, j) for p, j, _ in picked]
    fields = {"related_policies": [_brief(p, j, ctx.profile, ctx.as_of) for p, j in pairs],
              "manual_checks": _manual_checks([j for _, j in pairs])}
    docs = [_policy_doc(deps, p, text) for p, _, text in picked]
    status, checked = _generate(deps, question, docs, tag="policy", id_key="policyId", source_kind=SOURCE_POLICY,
                                judgements=_judgement_rows(pairs))
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
                                source_kind=SOURCE_POLICY, judgements=_judgement_rows([(policy, judgement)]))
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
