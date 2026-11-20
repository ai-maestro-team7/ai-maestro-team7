"""직무 적합도 분석 (개발계획서1 F-02·F-04, mentoring-fit-review-learning Requirement 1~8, 이슈 #88).

순서는 코드가 정한다. 모델은 두 곳에서만 쓴다:
  1. 프로필·요건 읽기 (DB 정확 조회. 요건은 B 공고 스냅샷 또는 NCS 능력단위)
  2. [모델] 요건마다 프로필에 이미 있는 역량·근거 ID 고르기
  3. 연결 검사: 프로필에 없는 ID는 버린다. 근거 단계는 저장된 역량 상태로 코드가 정한다
  4. 점수(fit/score.py)·격차(fit/gaps.py)·지원자격(백엔드 evaluate_eligibility) 계산
  5. KB 검색: 그 직무의 NCS 설명을 job_role 필터로 찾아 출처·기준일을 붙인다
  6. [모델] 결과 설명 문장. 점수·분류를 바꾸지 못하고, 합격 확률처럼 보이는 문장은 버린다
  7. `ANALYSIS#` 저장
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ValidationError

from mentoring.core import tasks
from mentoring.core.documents import check_id
from mentoring.core.idempotency import run_idempotent
from mentoring.core.logs import log_event, user_hash
from mentoring.core.metrics import emit_metric
from mentoring.errors import MentoringError, ai_output_invalid, aws_service_error, invalid_input, not_found, \
    not_implemented
from mentoring.models import CareerProfile, EvidenceLevel, FactStatus, Task, TaskStatus, TaskType

from .gaps import classify_gaps
from .models import RequirementMatch
from .prompts import LINK_SYSTEM, SUMMARY_SYSTEM, build_link_user, build_summary_user
from .records import (
    POSTING_NOT_READY,
    W_BASIC_PROFILE_MISSING,
    W_ELIGIBILITY_UNAVAILABLE,
    W_EXPIRED,
    W_NCS_AMBIGUOUS,
    W_NO_EVIDENCE,
    W_NOT_POSTING,
    W_NOTICE,
    W_SOURCE_UNAVAILABLE,
    W_SUMMARY_UNAVAILABLE,
    AnalysisRequest,
    AnalysisWarning,
    Citation,
    EligibilityCondition,
    EvidenceQuote,
    JobFitAnalysis,
    LinkOut,
    LinkOutput,
    PostingLatestView,
    PostingSnapshotView,
    RequirementLink,
    SummaryOutput,
)
from .score import calculate_fit

FEATURE = "job_fit"
_NCS_CODE = re.compile(r"^\d{8}$")
_KIND_TO_CATEGORY = {"REQUIRED_SKILL": "REQUIRED", "PREFERRED_SKILL": "PREFERRED"}
_LEVEL_ORDER = [EvidenceLevel.EVIDENCED, EvidenceLevel.PARTIAL, EvidenceLevel.SELF_REPORTED]
_WARNING_TEXT = {
    W_EXPIRED: "마감된 공고예요. 분석은 그때 공고 기준이에요.",
    W_NCS_AMBIGUOUS: "직무 NCS 코드를 하나로 정하지 못했어요. 직무를 고르면 NCS 설명과 학습 경로를 볼 수 있어요.",
    W_NO_EVIDENCE: "이 직무의 공식 설명 자료를 찾지 못했어요.",
    W_SOURCE_UNAVAILABLE: "공식 직무 자료 검색을 지금 쓸 수 없어 정형 데이터로만 분석했어요.",
    W_ELIGIBILITY_UNAVAILABLE: "지원자격 판정을 지금 할 수 없어요. 공고문에서 직접 확인해 주세요.",
    W_BASIC_PROFILE_MISSING: "기본 프로필(학력·전공·경력)이 없어 지원자격은 확인이 필요해요.",
    W_NOT_POSTING: "NCS 직무 기준 분석이라 특정 기업의 지원 조건은 반영하지 않았어요.",
    W_SUMMARY_UNAVAILABLE: "설명 문장을 만들지 못했어요. 아래 항목을 확인해 주세요.",
}


@dataclass
class FitOutcome:
    status: TaskStatus
    result_id: str
    review_reason: str | None
    retry_count: int


def _require(value, name: str):
    if value is None:
        raise not_implemented()
    return value


def _warn(code: str, deps=None) -> AnalysisWarning:
    if code == W_NOTICE:
        return AnalysisWarning(code=code, message=deps.config.job_fit.notice)
    return AnalysisWarning(code=code, message=_WARNING_TEXT[code])


# ---------------------------------------------------------------- 요청 (POST /analyses → 202)
def _load_profile(deps, user_id: str, profile_id: str, version: int | None) -> CareerProfile:
    pointer = deps.users.get_profile_pointer(user_id)
    if pointer is None or pointer.latest_profile_id != profile_id:
        raise not_found("역량 프로필을 찾을 수 없어요.")
    profile = deps.users.get_profile_version(user_id, profile_id, version or pointer.latest_version)
    if profile is None or profile.owner_user_id != user_id:
        raise not_found("역량 프로필을 찾을 수 없어요.")
    return profile


def create_analysis(deps, user_id: str, request: AnalysisRequest, idempotency_key: str | None = None) -> dict:
    store = _require(deps.analyses, "analyses")
    check_id(request.profile_id, "profileId")
    check_id(request.job_posting_id, "jobPostingId")
    check_id(request.workspace_id, "workspaceId")
    if not request.job_posting_id and not request.target_ncs_code:
        raise invalid_input("공고 또는 NCS 직무를 하나 골라 주세요.", missingInputs=["jobPostingId", "targetNcsCode"])
    if request.target_ncs_code is not None and not _NCS_CODE.match(request.target_ncs_code):
        raise invalid_input("NCS 직무 코드 형식이 올바르지 않아요.", field="targetNcsCode")

    # 멱등 해시는 사용자가 보낸 값 그대로 만든다. 생략한 profileVersion을 현재 최신
    # 버전으로 바꾸면 프로필 갱신 뒤 같은 키를 재시도할 때 다른 요청으로 오인한다.
    payload = {"profileId": request.profile_id, "profileVersion": request.profile_version,
               "jobPostingId": request.job_posting_id, "targetNcsCode": request.target_ncs_code,
               "workspaceId": request.workspace_id}

    def create() -> dict:
        # 최신 버전과 공고 스냅샷은 이 멱등 요청을 처음 만들 때만 고정한다.
        # REPLAY는 이 콜백을 실행하지 않고 처음 생성한 ID를 그대로 반환한다.
        profile = _load_profile(deps, user_id, request.profile_id, request.profile_version)
        latest = None
        if request.job_posting_id:
            catalog = _require(deps.catalog, "catalog")
            raw = catalog.get_latest(request.job_posting_id)
            if raw is None:
                raise not_found("공고를 찾을 수 없어요.")
            latest = PostingLatestView.model_validate(raw)
        if request.target_ncs_code:
            ncs = _require(deps.ncs, "ncs")
            if ncs.get_job_profile(request.target_ncs_code) is None:  # UT-09
                raise invalid_input("NCS 직무 코드를 찾을 수 없어요.", field="targetNcsCode")

        now = deps.now_iso()
        analysis_id = deps.new_id("analysis")
        task_id = f"task-{analysis_id}-fit"
        analysis = JobFitAnalysis(
            analysis_id=analysis_id, owner_user_id=user_id, status=TaskStatus.PENDING, task_id=task_id,
            assessment_mode="POSTING" if latest else "NCS_GENERAL",
            profile_id=profile.profile_id, profile_version=profile.profile_version,
            workspace_id=request.workspace_id,
            job_posting_id=latest.job_posting_id if latest else None,
            snapshot_id=latest.snapshot_id if latest else None,  # 요청한 시점의 공고를 고정한다 (UT-19)
            is_expired=latest.is_expired if latest else None,
            requested_ncs_code=request.target_ncs_code, created_at=now, updated_at=now)
        task = Task(task_id=task_id, task_type=TaskType.JOB_FIT, status=TaskStatus.PENDING, owner_user_id=user_id,
                    resource_id=analysis_id, resource_version=1, created_at=now, updated_at=now)
        store.create_analysis(analysis)
        deps.users.create_task(task)
        deps.tasks.dispatch(tasks.build_message(task))
        log_event("fit.requested", userHash=user_hash(deps, user_id), taskId=task_id, feature=FEATURE,
                  mode=analysis.assessment_mode)
        return {"analysisId": analysis_id, "taskId": task_id, "status": TaskStatus.PENDING.value}

    return run_idempotent(deps, user_id, idempotency_key, payload, create)


# ---------------------------------------------------------------- 실행 (작업 JOB_FIT)
def run_job_fit(deps, task: Task) -> FitOutcome:
    started = time.perf_counter()
    uid = task.owner_user_id
    store = _require(deps.analyses, "analyses")
    analysis = store.get_analysis(uid, task.resource_id)
    if analysis is None or analysis.owner_user_id != uid:  # 작업을 처리할 때 소유권을 다시 확인한다 (A §10.1)
        raise not_found()
    analysis = _save(deps, analysis, status=TaskStatus.PROCESSING)
    profile = deps.users.get_profile_version(uid, analysis.profile_id, analysis.profile_version)
    if profile is None:
        raise not_found("역량 프로필을 찾을 수 없어요.")

    cfg = deps.config.job_fit
    warnings = [_warn(W_NOTICE, deps)]
    update: dict = {}
    eligibility: dict = {}

    if analysis.assessment_mode == "POSTING":
        catalog = _require(deps.catalog, "catalog")
        raw = catalog.get_snapshot(analysis.job_posting_id, analysis.snapshot_id)
        if raw is None:
            raise not_found("공고를 찾을 수 없어요.")
        posting = PostingSnapshotView.model_validate(raw)
        update.update(posting_title=posting.title, organization=posting.organization,
                      official_url=posting.official_url, closes_at=posting.closes_at,
                      source_checked_at=posting.checked_at)
        if analysis.is_expired:
            warnings.append(_warn(W_EXPIRED))
        if posting.extract_status != "DONE":  # 요건 추출 전 스냅샷은 점수를 내지 않는다 [D-39 PROPOSED]
            analysis = _save(deps, analysis, status=TaskStatus.REQUIRES_USER_REVIEW, review_reason=POSTING_NOT_READY,
                             warnings=warnings, completed_at=deps.now_iso(), **update)
            return FitOutcome(TaskStatus.REQUIRES_USER_REVIEW, analysis.analysis_id, POSTING_NOT_READY, 0)
        requirements = [
            {"requirement_id": r.requirement_id, "name": r.name, "category": _KIND_TO_CATEGORY[r.kind],
             "weight": r.weight if r.weight and r.weight > 0 else 1.0, "source_quote": r.source_quote}
            for r in posting.requirements if r.kind in _KIND_TO_CATEGORY
        ]
        ncs_code, candidates = _pick_ncs(analysis.requested_ncs_code, posting.job.ncs_codes)
        if ncs_code is None:
            warnings.append(_warn(W_NCS_AMBIGUOUS))
        eligibility = _eligibility(deps, uid, profile, posting.eligibility_rules, warnings)
    else:
        ncs = _require(deps.ncs, "ncs")
        ncs_code, candidates = analysis.requested_ncs_code, []
        warnings.append(_warn(W_NOT_POSTING))
        requirements = [
            {"requirement_id": unit.unit_code, "name": unit.name, "category": "REQUIRED", "weight": 1.0,
             "ncs_unit_code": unit.unit_code}
            for unit in ncs.list_units(ncs_code)
        ]
    requirements = requirements[:cfg.max_requirements]

    ncs_name = None
    if ncs_code and deps.ncs is not None:
        job_profile = deps.ncs.get_job_profile(ncs_code)
        ncs_name = job_profile.name if job_profile else None
    update.update(ncs_code=ncs_code, ncs_name=ncs_name, ncs_candidates=candidates)

    links, calls, dropped_ids = _link(deps, task, requirements, profile)
    matches = [RequirementMatch(requirement_id=link.requirement_id, category=link.category,
                                weight=Decimal(str(link.weight)), evidence_level=link.evidence_level,
                                evidence_ids=[e.evidence_id for e in link.evidence]) for link in links]
    score = calculate_fit(matches)  # LLM 없이 규칙 코드로만 (Requirement 5)
    gaps = classify_gaps(matches)

    hits = _knowledge(deps, ncs_name, warnings)
    citations = _citations(deps, hits)

    result = analysis.model_copy(update={
        **update, "requirements": links, "score_status": score.status, "fit_score": score.fit_score,
        "potential_upper_bound": score.potential_upper_bound, "score_policy_version": score.score_policy_version,
        "category_breakdown": dict(score.category_breakdown), "gaps": gaps,
        "eligibility_status": eligibility.get("status"), "eligibility_conditions": eligibility.get("conditions", []),
        "rule_version": eligibility.get("rule_version"), "sources": citations,
        "model_id": getattr(deps.llm, "model_id", None),
        "prompt_version": f"{cfg.link_prompt_version}+{cfg.summary_prompt_version}"})
    summary, summary_calls = _summary(deps, result, hits)
    if summary is None:
        warnings.append(_warn(W_SUMMARY_UNAVAILABLE))
    analysis = _save(deps, result, status=TaskStatus.COMPLETED, summary=summary, warnings=warnings,
                     completed_at=deps.now_iso())

    if dropped_ids:
        emit_metric(deps, "EvidenceValidationFailure", dropped_ids, feature=FEATURE)
    emit_metric(deps, "AnalysisLatency", round((time.perf_counter() - started) * 1000, 1), feature=FEATURE)
    log_event("fit.analyzed", userHash=user_hash(deps, uid), taskId=task.task_id, feature=FEATURE,
              status=TaskStatus.COMPLETED.value, mode=analysis.assessment_mode, modelId=analysis.model_id,
              promptVersion=analysis.prompt_version, scorePolicyVersion=analysis.score_policy_version,
              ruleVersion=analysis.rule_version, retryCount=calls - 1 if calls else 0,
              counts={"requirements": len(links), "notFound": len(gaps.verification_tasks),
                      "droppedIds": dropped_ids, "sources": len(citations), "summaryCalls": summary_calls},
              warnings=[w.code for w in warnings])
    return FitOutcome(TaskStatus.COMPLETED, analysis.analysis_id, None, max(calls - 1, 0))


def mark_failed(deps, task: Task, code: str) -> None:
    """작업이 실패하면 분석에도 실패를 남긴다 (화면이 분석 상태만 봐도 알 수 있게)."""
    if deps.analyses is None:
        return
    analysis = deps.analyses.get_analysis(task.owner_user_id, task.resource_id)
    if analysis is not None:
        _save(deps, analysis, status=TaskStatus.FAILED, error_code=code, completed_at=deps.now_iso())


def _save(deps, analysis: JobFitAnalysis, **changes) -> JobFitAnalysis:
    updated = analysis.model_copy(update={**changes, "updated_at": deps.now_iso()})
    deps.analyses.save_analysis(updated)
    return updated


def _pick_ncs(requested: str | None, codes: list[str]) -> tuple[str | None, list[str]]:
    """공고의 NCS 코드가 하나면 그것을 쓴다. 0개·여러 개면 정하지 않고 후보로 남긴다 (Requirement 2 기준 7)."""
    unique = list(dict.fromkeys(c for c in codes if c))
    if requested:
        return requested, unique
    if len(unique) == 1:
        return unique[0], []
    return None, unique


# ---------------------------------------------------------------- 요건–근거 연결
def _parse(raw, model: type[BaseModel]):
    if not isinstance(raw, str):
        return None
    text = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        return model.model_validate(json.loads(text[start:end + 1]))
    except (ValueError, ValidationError):
        return None


def _invoke(deps, system: str, user: str, max_tokens: int) -> str:
    try:
        return deps.llm.invoke(system, user, max_tokens=max_tokens)
    except MentoringError:
        raise
    except Exception:  # noqa: BLE001 - Bedrock 오류 종류와 관계없이 다시 시도할 수 있는 오류로 남긴다
        raise aws_service_error("bedrock") from None


def _default_question(name: str) -> str:
    return f"'{name}'와 관련해 직접 해 본 경험이 있나요?"


def _link(deps, task: Task, requirements: list[dict], profile: CareerProfile) -> tuple[list[RequirementLink], int, int]:
    """모델은 프로필에 있는 ID만 고른다. 근거 단계는 연결된 역량의 저장 상태로 코드가 정한다 (Requirement 4)."""
    cfg = deps.config.job_fit
    skills = profile.skills[:cfg.max_profile_skills]
    skills_by_id = {s.skill_id: s for s in skills}
    evidence_by_id = {e.evidence_id: e for e in profile.evidence}
    outs: dict = {}
    calls = 0
    # NCS 능력단위 코드가 같은 역량은 모델 없이 코드로 연결한다 (#104). 같은 입력이면 항상 같은 연결
    by_code: dict[str, list] = {}
    for s in skills:
        if s.ncs_unit_code and s.evidence_level != EvidenceLevel.USER_CONFIRMED_GAP:
            by_code.setdefault(s.ncs_unit_code, []).append(s)
    for req in requirements:
        matched = by_code.get(req.get("ncs_unit_code") or "")
        if matched:
            outs[req["requirement_id"]] = LinkOut(
                requirement_id=req["requirement_id"], skill_ids=[s.skill_id for s in matched],
                evidence_ids=[i for s in matched for i in s.evidence_ids])
    pending = [r for r in requirements if r["requirement_id"] not in outs]
    if pending and skills:
        mask = deps.text.mask_pii
        req_view = [{"requirementId": r["requirement_id"], "name": r["name"],
                     **({"sourceQuote": r["source_quote"]} if r.get("source_quote") else {})} for r in pending]
        skill_view = [{"skillId": s.skill_id, "name": mask(s.name).masked_text,
                       "evidence": [{"evidenceId": i, "quotedText": mask(evidence_by_id[i].quoted_text).masked_text}
                                    for i in s.evidence_ids if i in evidence_by_id]}
                      for s in skills if s.evidence_level != EvidenceLevel.USER_CONFIRMED_GAP]
        problems = None
        failures = 0
        while True:
            calls += 1
            output = _parse(_invoke(deps, LINK_SYSTEM, build_link_user(req_view, skill_view, problems),
                                    cfg.link_max_tokens), LinkOutput)
            if output is not None:
                break
            failures += 1
            emit_metric(deps, "LLMSchemaFailure", 1, feature=FEATURE)
            log_event("fit.validation", userHash=user_hash(deps, task.owner_user_id), taskId=task.task_id,
                      feature=FEATURE, validation="SCHEMA_INVALID", retryCount=calls - 1)
            if failures > cfg.schema_retries:
                raise ai_output_invalid()
            problems = ["출력이 정해진 JSON 형식과 맞지 않았다"]
        pending_ids = {r["requirement_id"] for r in pending}
        for out in output.links:
            if out.requirement_id in pending_ids:  # 코드로 연결한 요건은 모델이 바꾸지 못한다
                outs.setdefault(out.requirement_id, out)

    # 사용자가 "없다"고 확인한 역량은 이름이 같은 요건에서 확인된 격차로 쓴다
    gap_names = {_norm(s.name) for s in profile.skills if s.evidence_level == EvidenceLevel.USER_CONFIRMED_GAP}
    links: list[RequirementLink] = []
    dropped = 0
    for req in requirements:
        out = outs.get(req["requirement_id"])
        chosen = []
        evidence_ids: list[str] = []
        question = None
        if out is not None:
            for skill_id in out.skill_ids:
                skill = skills_by_id.get(skill_id)
                if skill is None or skill in chosen:
                    dropped += skill is None
                    continue
                chosen.append(skill)
            allowed = {i for s in chosen for i in s.evidence_ids}
            for evidence_id in out.evidence_ids:
                if evidence_id in allowed and evidence_id in evidence_by_id:
                    if evidence_id not in evidence_ids:
                        evidence_ids.append(evidence_id)
                else:
                    dropped += 1
            question = (out.question or "").strip()[:cfg.question_max_chars] or None
        if chosen and not evidence_ids:
            evidence_ids = list(dict.fromkeys(i for s in chosen for i in s.evidence_ids if i in evidence_by_id))[:3]
        level = _level(chosen)
        if level == EvidenceLevel.NOT_FOUND and _norm(req["name"]) in gap_names:
            level = EvidenceLevel.USER_CONFIRMED_GAP
        if level in (EvidenceLevel.NOT_FOUND,):
            question = question or _default_question(req["name"])
        else:
            question = None
        links.append(RequirementLink(
            requirement_id=req["requirement_id"], name=req["name"], category=req["category"], weight=req["weight"],
            source_quote=req.get("source_quote"), ncs_unit_code=req.get("ncs_unit_code"), evidence_level=level,
            skill_ids=[s.skill_id for s in chosen], skill_names=[s.name for s in chosen],
            evidence=[EvidenceQuote(evidence_id=i, quoted_text=evidence_by_id[i].quoted_text) for i in evidence_ids]
            if level in _LEVEL_ORDER else [],
            question=question))
    return links, calls, dropped


def _level(skills) -> EvidenceLevel:
    levels = {s.evidence_level for s in skills}
    for level in _LEVEL_ORDER:
        if level in levels:
            return level
    if EvidenceLevel.USER_CONFIRMED_GAP in levels:
        return EvidenceLevel.USER_CONFIRMED_GAP
    return EvidenceLevel.NOT_FOUND


def _norm(text: str) -> str:
    return "".join(str(text).lower().split())


# ---------------------------------------------------------------- 지원자격 (Requirement 3)
def _eligibility(deps, user_id: str, profile: CareerProfile, rules: list[dict], warnings: list) -> dict:
    if deps.eligibility is None:
        warnings.append(_warn(W_ELIGIBILITY_UNAVAILABLE))
        return {"status": "NEEDS_VERIFICATION"}
    basic = deps.analyses.get_basic_profile(user_id)
    if basic is None:
        warnings.append(_warn(W_BASIC_PROFILE_MISSING))
        return {"status": "NEEDS_VERIFICATION"}
    merged = {key: basic.get(key) for key in ("educationLevel", "careerYears", "major") if basic.get(key) is not None}
    # 자격: 이력서 원문 인용이 붙은 자격만 보유로 본다 (모델 제안만 있는 것은 제외).
    # 사용자가 "없다"고 확인한 것(USER_CONFIRMED_GAP)은 보유 목록에서 빼고 미보유로 넘긴다 (db-schema §3.2)
    missing = [s.name for s in profile.skills if s.evidence_level == EvidenceLevel.USER_CONFIRMED_GAP]
    missing_norm = {_norm(name) for name in missing}
    merged["certificates"] = [c.name for c in profile.certificates
                              if c.evidence_ids and c.fact_status != FactStatus.SUGGESTION
                              and _norm(c.name) not in missing_norm]
    merged["confirmedMissingCertificates"] = missing
    try:
        result = deps.eligibility(merged, list(rules))
    except Exception as error:  # noqa: BLE001 - 판정 함수가 실패해도 분석은 계속하고 확인 필요로 둔다
        log_event("fit.eligibility_error", userHash=user_hash(deps, user_id), feature=FEATURE,
                  errorCode=type(error).__name__)
        warnings.append(_warn(W_ELIGIBILITY_UNAVAILABLE))
        return {"status": "NEEDS_VERIFICATION"}
    status = result.get("status")
    if status not in ("ELIGIBLE", "INELIGIBLE", "NEEDS_VERIFICATION"):
        status = "NEEDS_VERIFICATION"
    conditions = [EligibilityCondition.model_validate(c) for c in result.get("conditions") or []]
    return {"status": status, "conditions": conditions, "rule_version": result.get("ruleVersion")}


# ---------------------------------------------------------------- KB 근거 (Requirement 7)
def _knowledge(deps, ncs_name: str | None, warnings: list) -> list:
    if not ncs_name:
        return []  # 직무가 정해지지 않으면 다른 직무 문서가 섞이지 않게 검색하지 않는다 (UT-10)
    if deps.knowledge is None:
        warnings.append(_warn(W_SOURCE_UNAVAILABLE))
        return []
    try:
        hits = deps.knowledge.retrieve(f"{ncs_name} 직무의 주요 업무와 필요한 능력단위", job_role=ncs_name,
                                       k=deps.config.job_fit.kb_top_k)
    except Exception:  # noqa: BLE001 - KB가 안 되면 정형 데이터만으로 결과를 만든다 (Requirement 7 기준 8)
        warnings.append(_warn(W_SOURCE_UNAVAILABLE))
        return []
    hits = [h for h in hits if h.job_role in (ncs_name, "공통")]  # 필터가 빠져도 다른 직무 문서는 쓰지 않는다
    if not hits:
        warnings.append(_warn(W_NO_EVIDENCE))
        emit_metric(deps, "KbNoEvidence", 1, feature=FEATURE)
    return hits


def _citations(deps, hits) -> list[Citation]:
    now = deps.now_iso()
    size = deps.config.job_fit.citation_excerpt_chars
    seen: set[str] = set()
    result = []
    for hit in hits:
        if hit.document_id in seen:
            continue
        seen.add(hit.document_id)
        result.append(Citation(
            document_id=hit.document_id, document_type=hit.document_type,
            role="NCS_JOB_PROFILE" if hit.document_type == "ncs_job_profile" else "GUIDANCE",
            source_url=hit.source_url, checked_at=hit.collected_at,
            excerpt=(hit.text[:size] or None) if size else None, retrieved_at=now))
    return result


# ---------------------------------------------------------------- 설명 문장 (Requirement 5 기준 8)
def _summary(deps, analysis: JobFitAnalysis, hits) -> tuple[str | None, int]:
    from mentoring.knowledge import format_for_prompt

    cfg = deps.config.job_fit
    by_id = {r.requirement_id: r.name for r in analysis.requirements}
    gaps = analysis.gaps

    def names(items):
        return [by_id[i.requirement_id] for i in items]

    facts = {
        "assessmentMode": analysis.assessment_mode, "postingTitle": analysis.posting_title,
        "organization": analysis.organization, "ncsJob": analysis.ncs_name,
        "fitScore": analysis.fit_score, "potentialUpperBound": analysis.potential_upper_bound,
        "eligibilityStatus": analysis.eligibility_status,
        "strengths": names(gaps.confirmed_strengths), "partialEvidence": names(gaps.partial_evidence),
        "needsConfirmation": names(gaps.verification_tasks), "confirmedGaps": names(gaps.confirmed_gaps),
        "unmetEligibility": [c.reason for c in analysis.eligibility_conditions if c.result == "NOT_MET"],
    }
    banned = [re.compile(p) for p in cfg.banned_summary_patterns]
    problems = None
    calls = 0
    for _ in range(cfg.summary_retries + 1):
        calls += 1
        try:
            raw = _invoke(deps, SUMMARY_SYSTEM, build_summary_user(facts, format_for_prompt(hits), problems),
                          cfg.summary_max_tokens)
        except MentoringError:
            return None, calls  # 설명이 없어도 점수와 항목은 보여 준다
        output = _parse(raw, SummaryOutput)
        if output is None:
            problems = ["출력이 정해진 JSON 형식과 맞지 않았다"]
            continue
        text = output.summary.strip()
        if any(p.search(text) for p in banned):
            problems = ["합격 확률·가능성이나 퍼센트로 표현했다. 그런 표현 없이 다시 쓴다"]
            continue
        if not text or len(text) > cfg.summary_max_chars:
            problems = [f"설명이 비었거나 {cfg.summary_max_chars}자를 넘었다"]
            continue
        return text, calls
    return None, calls


# ---------------------------------------------------------------- 조회 (GET /analyses/{id})
def get_analysis(deps, user_id: str, analysis_id: str) -> JobFitAnalysis:
    store = _require(deps.analyses, "analyses")
    check_id(analysis_id, "analysisId")
    analysis = store.get_analysis(user_id, analysis_id)
    if analysis is None or analysis.owner_user_id != user_id:
        raise not_found()
    return analysis


def analysis_view(analysis: JobFitAnalysis) -> dict:
    """API 응답 (개발계획서1 §6.3 필드 이름). 지원자격은 점수보다 앞에 둔다 (Requirement 3 기준 5)."""
    base = {"analysisId": analysis.analysis_id, "status": analysis.status.value, "taskId": analysis.task_id,
            "assessmentMode": analysis.assessment_mode, "profileId": analysis.profile_id,
            "profileVersion": analysis.profile_version, "createdAt": analysis.created_at,
            "updatedAt": analysis.updated_at}
    if analysis.workspace_id:
        base["workspaceId"] = analysis.workspace_id
    if analysis.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):
        return base
    if analysis.status == TaskStatus.FAILED:
        return {**base, "errorCode": analysis.error_code}

    links = {r.requirement_id: r for r in analysis.requirements}

    def item(gap, *, with_question=False):
        link = links[gap.requirement_id]
        data = {"requirementId": link.requirement_id, "name": link.name, "category": link.category,
                "evidenceLevel": link.evidence_level.value}
        if link.source_quote:
            data["sourceQuote"] = link.source_quote
        if link.ncs_unit_code:
            data["ncsUnitCode"] = link.ncs_unit_code
        if link.evidence:
            data["evidenceIds"] = [e.evidence_id for e in link.evidence]
            data["evidence"] = [e.to_api() for e in link.evidence]
        if link.skill_names:
            data["skills"] = list(link.skill_names)
        if with_question and link.question:
            data["question"] = link.question
        return data

    unmet = [{"kind": "ELIGIBILITY", **c.to_api()} for c in analysis.eligibility_conditions if c.result == "NOT_MET"]
    gaps = analysis.gaps
    body = {**base}
    if analysis.assessment_mode == "POSTING":
        body["posting"] = {k: v for k, v in {
            "jobPostingId": analysis.job_posting_id, "snapshotId": analysis.snapshot_id,
            "title": analysis.posting_title, "organization": analysis.organization,
            "officialUrl": analysis.official_url, "closesAt": analysis.closes_at,
            "isExpired": analysis.is_expired, "checkedAt": analysis.source_checked_at}.items() if v is not None}
    body["ncs"] = {k: v for k, v in {"code": analysis.ncs_code, "name": analysis.ncs_name,
                                     "candidates": analysis.ncs_candidates or None}.items() if v is not None}
    if analysis.status == TaskStatus.REQUIRES_USER_REVIEW:
        return {**body, "reviewReason": analysis.review_reason,
                "nextAction": "공고 요건을 정리하는 중이에요. 잠시 후 다시 분석해 주세요.",
                "warnings": [w.to_api() for w in analysis.warnings]}
    body["eligibility"] = {k: v for k, v in {
        "status": analysis.eligibility_status, "ruleVersion": analysis.rule_version,
        "unmet": unmet or None,
        "conditions": [c.to_api() for c in analysis.eligibility_conditions] or None}.items() if v is not None}
    body.update({
        "scoreType": analysis.score_type, "scoreStatus": analysis.score_status, "fitScore": analysis.fit_score,
        "potentialUpperBound": analysis.potential_upper_bound, "scorePolicyVersion": analysis.score_policy_version,
        "categoryBreakdown": {k: v.to_api() for k, v in analysis.category_breakdown.items()},
        "strengths": [item(g) for g in gaps.confirmed_strengths] if gaps else [],
        "partialEvidence": [item(g) for g in gaps.partial_evidence] if gaps else [],
        "unverifiedSkills": [item(g, with_question=True) for g in gaps.verification_tasks] if gaps else [],
        "confirmedGaps": unmet + ([item(g) for g in gaps.confirmed_gaps] if gaps else []),
        "summary": analysis.summary,
        "sources": [c.to_api() for c in analysis.sources],
        "warnings": [w.to_api() for w in analysis.warnings],
        "modelId": analysis.model_id, "promptVersion": analysis.prompt_version,
        "schemaVersion": analysis.schema_version, "completedAt": analysis.completed_at,
    })
    if analysis.source_checked_at:
        body["sourceCheckedAt"] = analysis.source_checked_at
    return body
