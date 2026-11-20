"""역량 격차 → 학습·자격 경로 (개발계획서1 F-04·F-05, mentoring-fit-review-learning Requirement 12~14, 이슈 #113).

순서는 코드가 정한다. 모델은 4번 문장에서만 쓴다:
  1. 적합도 분석의 격차에서 학습 대상(확인된 격차, 미충족 자격 조건, 증빙 보완)과 먼저 확인할 것(미확인)을 나눈다
  2. 공고 기준 분석이면 그 직무의 NCS 능력단위 중 아직 근거가 없는 것을 학습 목표로 더한다 (공식 정형 데이터)
  3. 주 수·주차 배정·주당 시간은 코드가 계산한다. 훈련시간은 참고값이고 개인 학습 기간이 아니다
  4. [모델] 주차별 목표·실습·산출물 문장. 실패하면 정해진 문장으로 대신하고 PARTIAL_SUCCESS
  5. 자격 후보: NCS 능력단위–자격 연계(중복 제거) 중 자격 정보가 있는 것만. 공고 필수 자격으로 표시하지 않는다
  6. 시험일정: #95가 매일 모아 둔 캐시만 읽는다. 없거나 지났거나 기한이 지난 자료면 SCHEDULE_UNVERIFIED, 날짜를 만들지 않는다
  7. 교육과정(고용24)은 MVP에서 연결하지 않는다 → courses=[], NO_LIVE_COURSES. 부산 청년정책은 B 정책 지갑 링크 (M-10)
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from mentoring.core import tasks
from mentoring.core.documents import check_id
from mentoring.core.idempotency import run_idempotent
from mentoring.core.logs import log_event, user_hash
from mentoring.core.metrics import emit_metric
from mentoring.errors import MentoringError, invalid_input, not_found, not_implemented, precondition_not_met
from mentoring.fit.records import AnalysisWarning
from mentoring.llm.structured import invoke, parse_json
from mentoring.models import Task, TaskStatus, TaskType
from mentoring.store.results import result_item

from .models import (
    CertificateCandidate,
    ExamRound,
    LearningPathRecord,
    LearningPathRequest,
    LearningTarget,
    PlanOutput,
    VerificationTask,
    Week,
)
from .prompts import PLAN_SYSTEM, build_plan_user

FEATURE = "learning_path"
PREFIX, ENTITY = "PATH", "LEARNING_PATH"
_KIND_LABEL = {"CONFIRMED_GAP": "확인된 격차", "ELIGIBILITY_GAP": "지원 조건", "STRENGTHEN_EVIDENCE": "증빙 보완",
               "NCS_UNIT": "NCS 학습 목표", "DEEPEN_STRENGTH": "강점 심화"}
_WARNINGS = {
    "ESTIMATED": "기간과 시간은 주당 학습 시간으로 계산한 추정이에요. NCS 훈련시간은 참고값이에요.",
    "NO_LIVE_COURSES": "모집 중인 교육과정은 아직 연결하지 않았어요. 실습 계획만 드려요.",
    "SCHEDULE_UNVERIFIED": "일부 자격은 시험 일정을 확인하지 못했어요. 공식 안내에서 직접 확인해 주세요.",
    "RESULT_AFTER_DEADLINE": "일부 시험은 합격 발표가 공고 마감 뒤예요. 공고의 자격 인정 기준일을 확인해 주세요.",
    "NCS_LINK_NOTE": "추천 자격은 NCS 능력단위와 연계된 자격이에요. 이 공고의 필수 자격이라는 뜻은 아니에요.",
    "VERIFY_FIRST": "서류에서 확인되지 않은 항목이 있어요. 학습 전에 먼저 경험이 있는지 확인해 주세요.",
    "NO_GAPS": "확인된 격차가 없어 강점을 더 깊게 다지는 계획을 드려요.",
    "PLAN_TEXT_FALLBACK": "주차별 설명을 만들지 못해 기본 문장으로 채웠어요.",
    "EXAM_SOURCE_FAILED": "시험 일정 자료를 읽지 못했어요.",
}


@dataclass
class PathOutcome:
    status: TaskStatus
    result_id: str
    review_reason: str | None
    retry_count: int


def _store(deps):
    if deps.results is None or deps.analyses is None:
        raise not_implemented()
    return deps.results


def _warn(code: str) -> AnalysisWarning:
    return AnalysisWarning(code=code, message=_WARNINGS[code])


def _as_of(deps) -> date:
    return deps.now().date()


def _parse_date(value: str | None, field: str) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise invalid_input("날짜는 YYYY-MM-DD 형식으로 보내 주세요.", field=field) from None


def plan_weeks(start: date, target: date | None, cfg) -> int:
    """주 수 (코드 계산, Requirement 12 기준 4). 목표일이 없으면 기본 주 수."""
    if target is None:
        return cfg.default_weeks
    weeks = math.ceil((target - start).days / 7)
    return max(cfg.min_weeks, min(cfg.max_weeks, weeks))


def assign_targets(count: int, weeks: int) -> list[list[int]]:
    """주차마다 다룰 학습 대상 번호. 우선순위 순서를 지키며 고르게 나눈다."""
    if count == 0 or weeks == 0:
        return [[] for _ in range(weeks)]
    if weeks >= count:
        return [[w * count // weeks] for w in range(weeks)]
    slots: list[list[int]] = [[] for _ in range(weeks)]
    for i in range(count):
        slots[i * weeks // count].append(i)
    return slots


# ---------------------------------------------------------------- 요청 (POST /learning-paths → 202)
def create_learning_path(deps, user_id: str, request: LearningPathRequest, idempotency_key: str | None = None) -> dict:
    store = _store(deps)
    check_id(request.analysis_id, "analysisId")
    check_id(request.workspace_id, "workspaceId")
    analysis = deps.analyses.get_analysis(user_id, request.analysis_id)
    if analysis is None or analysis.owner_user_id != user_id:
        raise not_found("분석 결과를 찾을 수 없어요.")
    if analysis.status != TaskStatus.COMPLETED:
        raise precondition_not_met("적합도 분석이 끝난 뒤에 학습 경로를 만들 수 있어요.")
    as_of = _as_of(deps)
    start = _parse_date(request.start_date, "startDate") or as_of
    target = _parse_date(request.target_date, "targetDate")
    if start < as_of:
        raise invalid_input("시작일은 오늘 이후로 정해 주세요.", field="startDate")
    if target is not None and target <= start:
        raise invalid_input("목표일은 시작일보다 뒤여야 해요.", field="targetDate")

    ncs_code = request.ncs_code or analysis.ncs_code
    if analysis.ncs_code is None and analysis.ncs_candidates and ncs_code not in analysis.ncs_candidates:
        raise invalid_input("직무 NCS 코드를 후보 중에서 하나 골라 주세요.", field="ncsCode",
                            candidates=analysis.ncs_candidates)  # Requirement 12 기준 2
    ncs_name = None
    if ncs_code:
        profile = deps.ncs.get_job_profile(ncs_code) if deps.ncs is not None else None
        if deps.ncs is not None and profile is None:
            raise invalid_input("NCS 직무 코드를 찾을 수 없어요.", field="ncsCode")
        ncs_name = profile.name if profile else None

    payload = {**request.model_dump(by_alias=True, mode="json"), "ncsCode": ncs_code, "startDate": start.isoformat()}

    def create() -> dict:
        now = deps.now_iso()
        path_id = deps.new_id("path")
        task_id = f"task-{path_id}"
        record = LearningPathRecord(
            learning_path_id=path_id, owner_user_id=user_id, status=TaskStatus.PENDING, task_id=task_id,
            analysis_id=analysis.analysis_id, workspace_id=request.workspace_id, ncs_code=ncs_code,
            ncs_name=ncs_name, weekly_study_hours=request.weekly_study_hours,
            preferred_format=request.preferred_format, region_code=request.region_code,
            start_date=start.isoformat(), target_date=target.isoformat() if target else None,
            created_at=now, updated_at=now)
        task = Task(task_id=task_id, task_type=TaskType.LEARNING_PATH, status=TaskStatus.PENDING,
                    owner_user_id=user_id, resource_id=path_id, resource_version=1, created_at=now, updated_at=now)
        store.create(result_item(PREFIX, ENTITY, record, path_id))
        deps.users.create_task(task)
        deps.tasks.dispatch(tasks.build_message(task))
        log_event("learning.requested", userHash=user_hash(deps, user_id), taskId=task_id, feature=FEATURE)
        return {"learningPathId": path_id, "taskId": task_id, "status": TaskStatus.PENDING.value}

    return run_idempotent(deps, user_id, idempotency_key, payload, create)


# ---------------------------------------------------------------- 실행 (작업 LEARNING_PATH)
def _get_record(deps, user_id: str, path_id: str) -> LearningPathRecord | None:
    item = _store(deps).get(user_id, f"{PREFIX}#{path_id}")
    return LearningPathRecord.model_validate(item) if item else None


def _save(deps, record: LearningPathRecord, **changes) -> LearningPathRecord:
    updated = record.model_copy(update={**changes, "updated_at": deps.now_iso()})
    _store(deps).save(result_item(PREFIX, ENTITY, updated, updated.learning_path_id))
    return updated


def mark_failed(deps, task: Task, code: str) -> None:
    if deps.results is None:
        return
    record = _get_record(deps, task.owner_user_id, task.resource_id)
    if record is not None:
        _save(deps, record, status=TaskStatus.FAILED, error_code=code, completed_at=deps.now_iso())


def build_targets(deps, analysis, ncs_code: str | None) -> tuple[list[LearningTarget], list[VerificationTask], bool]:
    """(학습 대상, 먼저 확인할 것, 강점 심화 여부). F-02 결과만 쓰고 따로 추측하지 않는다 (F-04 완료 기준)."""
    cfg = deps.config.learning
    links = {r.requirement_id: r for r in analysis.requirements}
    gaps = analysis.gaps
    targets: list[LearningTarget] = []
    seen: set[str] = set()

    def add(kind, name, link=None, unit_code=None):
        key = (unit_code or "") + "|" + name
        if key in seen:
            return  # 같은 항목을 두 번 추천하지 않는다 (F-04 완료 기준)
        seen.add(key)
        targets.append(LearningTarget(
            target_id=f"t-{len(targets) + 1}", kind=kind, name=name, category=link.category if link else None,
            requirement_id=link.requirement_id if link else None,
            ncs_unit_code=unit_code or (link.ncs_unit_code if link else None)))

    for gap in gaps.confirmed_gaps if gaps else []:
        add("CONFIRMED_GAP", links[gap.requirement_id].name, links[gap.requirement_id])
    for cond in analysis.eligibility_conditions:
        if cond.result == "NOT_MET":
            add("ELIGIBILITY_GAP", cond.source_quote or cond.reason or "지원 조건")
    for gap in gaps.partial_evidence if gaps else []:
        add("STRENGTHEN_EVIDENCE", links[gap.requirement_id].name, links[gap.requirement_id])
    verification = [VerificationTask(requirement_id=g.requirement_id, name=links[g.requirement_id].name,
                                     question=links[g.requirement_id].question
                                     or f"'{links[g.requirement_id].name}' 관련 경험이 있나요?")
                    for g in (gaps.verification_tasks if gaps else [])]

    units = {}
    if ncs_code and deps.ncs is not None:
        units = {u.unit_code: u for u in deps.ncs.list_units(ncs_code)}
        if analysis.assessment_mode == "POSTING":
            covered = {r.ncs_unit_code for r in analysis.requirements if r.ncs_unit_code} | \
                      {t.ncs_unit_code for t in targets if t.ncs_unit_code}
            extra = [u for code, u in sorted(units.items()) if code not in covered][:cfg.max_units_per_posting]
            for unit in extra:
                add("NCS_UNIT", unit.name, unit_code=unit.unit_code)
    deepen = False
    if not targets and not verification:  # 격차가 없으면 강점 심화 (Requirement 12 기준 7)
        deepen = True
        for gap in gaps.confirmed_strengths if gaps else []:
            add("DEEPEN_STRENGTH", links[gap.requirement_id].name, links[gap.requirement_id])
    targets = targets[:cfg.max_targets]
    for target in targets:
        unit = units.get(target.ncs_unit_code or "")
        if unit is not None:
            target.reference_training_hours = unit.training_hours
    return targets, verification, deepen


def _fallback_week(week_targets: list[LearningTarget]) -> dict:
    names = ", ".join(t.name for t in week_targets) or "앞 주차 내용"
    return {"goals": [f"{names}의 기본 개념과 사용 방법을 정리한다"],
            "activities": [f"{names} 관련 공식 자료를 읽고 작은 실습 하나를 해 본다", "실습 과정과 결과를 기록한다"],
            "deliverable": f"{names} 실습 기록 1건"}


def _plan_text(deps, task, record, weeks: list[Week], targets_by_id: dict) -> tuple[dict[int, dict], int, bool]:
    """(주차 번호 → 문장, 호출 수, 대체 문장 사용 여부)."""
    cfg = deps.config.learning
    if not weeks:
        return {}, 0, False
    plan = {"weeklyStudyHours": record.weekly_study_hours, "preferredFormat": record.preferred_format,
            "weeks": [{"week": w.week, "hours": w.estimated_hours,
                       "targets": [{"name": targets_by_id[t].name, "kind": _KIND_LABEL[targets_by_id[t].kind]}
                                   for t in w.target_ids]} for w in weeks]}
    expected = {w.week for w in weeks}
    problems = None
    calls = 0
    for _ in range(cfg.schema_retries + 1):
        calls += 1
        try:
            raw = invoke(deps, PLAN_SYSTEM, build_plan_user(plan, problems), cfg.max_tokens)
        except MentoringError:
            break
        output = parse_json(raw, PlanOutput)
        if output is not None and {w.week for w in output.weeks} == expected:
            return {w.week: {"goals": [g.strip() for g in w.goals if g.strip()],
                             "activities": [a.strip() for a in w.activities if a.strip()],
                             "deliverable": (w.deliverable or "").strip() or None} for w in output.weeks}, calls, False
        emit_metric(deps, "LLMSchemaFailure", 1, feature=FEATURE)
        problems = [f"주차는 {sorted(expected)}을 하나씩 모두 써야 하고 정해진 JSON 형식이어야 한다"]
    log_event("learning.plan_fallback", userHash=user_hash(deps, record.owner_user_id), taskId=task.task_id,
              feature=FEATURE, retryCount=calls)
    return {w.week: _fallback_week([targets_by_id[t] for t in w.target_ids]) for w in weeks}, calls, True


def _ymd(value) -> str | None:
    text = str(value or "").strip()
    try:
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    except ValueError:
        return None


def exam_schedule(deps, code: str, as_of: date, closes_at: str | None) -> tuple[list[ExamRound] | None, str | None, bool]:
    """(앞으로의 시험 회차 또는 None, 자료 기준 시각, 자료 읽기 실패 여부). 날짜를 만들지 않는다 (UT-11)."""
    cfg = deps.config.learning
    if deps.exams is None:
        return None, None, False
    deadline = closes_at if closes_at and not closes_at.startswith("9999") else None
    now_ts = int(deps.now().timestamp())
    rounds: list[ExamRound] = []
    checked = None
    try:
        for year in range(as_of.year, as_of.year + cfg.exam_lookahead_years + 1):
            item = deps.exams.get(code, year)
            if not item or int(item.get("expires_at") or 0) < now_ts or not item.get("collectedAt"):
                continue  # 없거나 기한이 지난 자료는 확인된 일정으로 쓰지 않는다
            checked = item["collectedAt"]
            for row in item.get("items") or []:
                dates = {ours: d for raw, ours in cfg.exam_date_fields.items() if (d := _ymd(row.get(raw)))}
                if not dates or max(dates.values()) < as_of.isoformat():
                    continue
                result = dates.get("finalResultDate") or dates.get("writtenResultDate")
                rounds.append(ExamRound(round=str(row.get("description") or row.get("implSeq") or "") or None,
                                        dates=dates,
                                        result_after_posting_deadline=(result > deadline)
                                        if result and deadline else None))
    except Exception as error:  # noqa: BLE001 - 일정 자료가 안 돼도 학습 경로는 만든다 (F-05 완료 기준)
        log_event("learning.exam_error", feature=FEATURE, errorCode=type(error).__name__)
        emit_metric(deps, "OfficialSourceFailure", 1, feature=FEATURE)
        return None, None, True
    return (rounds or None), (checked if rounds else None), False


def build_certificates(deps, analysis, targets: list[LearningTarget], as_of: date) -> tuple[list[CertificateCandidate], bool]:
    cfg = deps.config.learning
    if deps.ncs is None:
        return [], False
    units = [t.ncs_unit_code for t in targets if t.ncs_unit_code]
    grouped: dict[str, list[str]] = {}
    seen: set[tuple[str, str, str]] = set()
    for unit in dict.fromkeys(units):
        for link in deps.ncs.list_qualification_links(unit):
            key = (link.unit_code, link.qualification_code, link.unit_type)
            if key in seen:
                continue  # (능력단위, 자격, 구분)으로 중복 제거 (UT-13)
            seen.add(key)
            grouped.setdefault(link.qualification_code, [])
            if link.unit_code not in grouped[link.qualification_code]:
                grouped[link.qualification_code].append(link.unit_code)
    quotes = " ".join(c.source_quote or "" for c in analysis.eligibility_conditions if c.type == "CERTIFICATE")
    result: list[CertificateCandidate] = []
    failed = False
    for code, linked in grouped.items():
        qual = deps.ncs.get_qualification(code)
        if qual is None:
            continue  # 자격 정보가 없는 후보는 넣지 않는다 (Requirement 13 기준 1)
        rounds, checked, err = exam_schedule(deps, code, as_of, analysis.closes_at)
        failed = failed or err
        required = bool(quotes) and "".join(qual.name.split()) in "".join(quotes.split())
        candidate_checked = checked or qual.collected_at
        if not candidate_checked:
            continue  # 기준일이 없는 항목은 뺀다 (Requirement 13 기준 8)
        result.append(CertificateCandidate(
            qualification_code=code, name=qual.name, exam_agency=qual.exam_agency, linked_unit_codes=linked,
            reason=("공고 지원 조건에 있는 자격이에요." if required else
                    "학습 대상 NCS 능력단위와 공식 연계된 자격이에요. 이 공고의 필수 자격은 아니에요."),
            required_by_posting=required, schedule=rounds,
            verification_status="VERIFIED" if rounds else "SCHEDULE_UNVERIFIED",
            official_url=qual.source_url or cfg.exam_guide_url, checked_at=candidate_checked))
        if len(result) >= cfg.max_certificates:
            break
    return result, failed


def run_learning_path(deps, task: Task) -> PathOutcome:
    started = time.perf_counter()
    cfg = deps.config.learning
    uid = task.owner_user_id
    record = _get_record(deps, uid, task.resource_id)
    if record is None or record.owner_user_id != uid:
        raise not_found()
    record = _save(deps, record, status=TaskStatus.PROCESSING)
    analysis = deps.analyses.get_analysis(uid, record.analysis_id)
    if analysis is None:
        raise not_found("분석 결과를 찾을 수 없어요.")
    as_of = _as_of(deps)
    start = date.fromisoformat(record.start_date)
    target = date.fromisoformat(record.target_date) if record.target_date else None

    targets, verification, deepen = build_targets(deps, analysis, record.ncs_code)
    n_weeks = plan_weeks(start, target, cfg) if targets else 0
    slots = assign_targets(len(targets), n_weeks)
    weeks = [Week(week=i + 1, start_date=(start + timedelta(days=7 * i)).isoformat(),
                  target_ids=[targets[j].target_id for j in slot], estimated_hours=record.weekly_study_hours,
                  official_sources=[{"type": "NCS_UNIT", "unitCode": targets[j].ncs_unit_code, "name": targets[j].name}
                                    for j in slot if targets[j].ncs_unit_code])
             for i, slot in enumerate(slots)]
    by_id = {t.target_id: t for t in targets}
    texts, calls, fallback = _plan_text(deps, task, record, weeks, by_id)
    weeks = [w.model_copy(update=texts.get(w.week, {})) for w in weeks]

    certificates, exam_failed = build_certificates(deps, analysis, targets, as_of)
    warnings = [_warn("ESTIMATED"), _warn("NO_LIVE_COURSES")]
    if verification:
        warnings.append(_warn("VERIFY_FIRST"))
    if deepen:
        warnings.append(_warn("NO_GAPS"))
    if certificates:
        warnings.append(_warn("NCS_LINK_NOTE"))
    if any(c.verification_status == "SCHEDULE_UNVERIFIED" for c in certificates):
        warnings.append(_warn("SCHEDULE_UNVERIFIED"))
    if any(r.result_after_posting_deadline for c in certificates for r in (c.schedule or [])):
        warnings.append(_warn("RESULT_AFTER_DEADLINE"))
    if exam_failed:
        warnings.append(_warn("EXAM_SOURCE_FAILED"))
    if fallback:
        warnings.append(_warn("PLAN_TEXT_FALLBACK"))

    if deps.exams is None:
        exam_status = "NOT_CONNECTED"
    elif exam_failed:
        exam_status = "FAILED"
    elif not certificates:
        exam_status = "NONE"
    elif all(c.verification_status == "VERIFIED" for c in certificates):
        exam_status = "VERIFIED"
    else:
        exam_status = "PARTIAL"
    status = TaskStatus.PARTIAL_SUCCESS if (exam_failed or fallback) else TaskStatus.COMPLETED
    # 주당 시간은 사용자가 정한 시간을 넘지 않고, 총 시간은 주당 시간 × 주 수다 (Requirement 12 기준 4)
    total_hours = sum(w.estimated_hours for w in weeks)
    _save(deps, record, status=status, targets=targets, verification_tasks=verification, weeks=weeks,
          total_weeks=len(weeks), total_hours=total_hours, certificates=certificates, courses=[],
          source_verification_status={"qualifications": "REFERENCE_DATA", "examSchedule": exam_status,
                                      "courses": "NOT_CONNECTED"},
          related_links=[{"type": "POLICY_WALLET", "path": cfg.policy_wallet_path,
                          "label": "부산 청년 지원 정책은 정책 지갑에서 확인해요"},
                         {"type": "EXAM_GUIDE", "url": cfg.exam_guide_url, "label": "국가자격 시험 공식 안내"}],
          warnings=warnings, model_id=getattr(deps.llm, "model_id", None) if calls else None,
          prompt_version=cfg.prompt_version, completed_at=deps.now_iso())
    emit_metric(deps, "AnalysisLatency", round((time.perf_counter() - started) * 1000, 1), feature=FEATURE)
    log_event("learning.completed", userHash=user_hash(deps, uid), taskId=task.task_id, feature=FEATURE,
              status=status.value, promptVersion=cfg.prompt_version, retryCount=max(calls - 1, 0),
              counts={"targets": len(targets), "weeks": len(weeks), "certificates": len(certificates),
                      "verification": len(verification)}, warnings=[w.code for w in warnings])
    return PathOutcome(status, record.learning_path_id, None, max(calls - 1, 0))


# ---------------------------------------------------------------- 조회 (GET /learning-paths/{id})
def get_learning_path(deps, user_id: str, path_id: str) -> dict:
    check_id(path_id, "learningPathId")
    record = _get_record(deps, user_id, path_id)
    if record is None or record.owner_user_id != user_id:
        raise not_found()
    return {k: v for k, v in record.to_api().items() if k != "ownerUserId"}

