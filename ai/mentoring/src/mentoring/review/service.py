"""자기소개서·이력서 첨삭 (개발계획서1 F-03, mentoring-fit-review-learning Requirement 9~11, 이슈 #113).

순서는 코드가 정한다. 모델은 4번에서만 쓴다:
  1. 원문 읽기 (문서의 정규화 텍스트 또는 요청 inputText) + 글자 수 계산 (코드)
  2. 기준 읽기: 분석이 고정한 공고 요건(또는 공고 스냅샷), 사용자가 확인한 경험 블록 필드, 확인된 역량
  3. 개인정보 가리기 (길이 보존)
  4. [모델] 문항 의도, 고칠 곳(원문 구간), 이유, 개선 방법, 수정 예시, 확인 질문
  5. 검사: 원문 구간이 실제로 있는지, 수정 예시의 숫자·기간·날짜가 원문·확인된 사실에 있는지 (없으면 예시를 빼고 질문으로)
  6. 블라인드 위험 표현을 규칙으로 한 번 더 찾는다
  7. 본문은 S3, 메타는 `REVIEW#`. 문서를 고치지 않는다 (사용자가 고른 최종본 저장은 워크스페이스 API, BACKEND)
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from mentoring.core import tasks
from mentoring.core.documents import check_id
from mentoring.core.idempotency import run_idempotent
from mentoring.core.logs import log_event, user_hash
from mentoring.core.metrics import emit_metric
from mentoring.errors import MentoringError, document_not_found, invalid_input, not_found, not_implemented, \
    precondition_not_met
from mentoring.fit.records import AnalysisWarning, PostingLatestView, PostingSnapshotView
from mentoring.llm.structured import call_structured
from mentoring.models import FactStatus, Task, TaskStatus, TaskType
from mentoring.store.results import result_item

from .models import (
    CharCount,
    PostingBasis,
    ReviewBody,
    ReviewIssue,
    ReviewOutput,
    ReviewRecord,
    ReviewRequest,
    SourceSpan,
)
from .prompts import REVIEW_SYSTEM, build_review_user

FEATURE = "review"
PREFIX, ENTITY = "REVIEW", "REVIEW"
REVIEW_SPAN_MISMATCH = "SPAN_MISMATCH"
_FOUND = {"EXACT", "RELOCATED"}
_STAR = ("situation", "task", "actions", "result", "learning")
_WARNINGS = {
    "NOT_POSTING_SPECIFIC": "공고를 고르지 않아 공고 맞춤 첨삭이 아니에요. 공고를 고르면 요건 기준으로 볼 수 있어요.",
    "LENGTH_OVER": "글자 수 제한을 넘었어요.",
    "FACT_CHECK": "수정 예시에 원문에서 확인되지 않는 내용이 있어 예시 대신 확인 질문을 드려요.",
    "DRAFT_NOTICE": "첨삭은 제안이에요. 제출 전에 내용이 사실인지 꼭 확인해 주세요.",
}


@dataclass
class ReviewOutcome:
    status: TaskStatus
    result_id: str
    review_reason: str | None
    retry_count: int


def _store(deps):
    if deps.results is None:
        raise not_implemented()
    return deps.results


def _key(deps, user_id: str, review_id: str, name: str) -> str:
    """S3 키는 서버만 만든다 (Requirement 2 기준 4)."""
    return f"users/{deps.hash_user_id(user_id)}/reviews/{review_id}/{name}"


def _warn(code: str) -> AnalysisWarning:
    return AnalysisWarning(code=code, message=_WARNINGS[code])


def count_chars(text: str, max_characters: int | None) -> CharCount:
    with_spaces = len(text)
    return CharCount(with_spaces=with_spaces, without_spaces=len(re.sub(r"\s", "", text)),
                     utf8_bytes=len(text.encode("utf-8")), max_characters=max_characters,
                     over_limit=bool(max_characters and with_spaces > max_characters))


# ---------------------------------------------------------------- 요청 (POST /reviews → 202)
def create_review(deps, user_id: str, request: ReviewRequest, idempotency_key: str | None = None) -> dict:
    store = _store(deps)
    cfg = deps.config.review
    for value, field in ((request.document_id, "documentId"), (request.analysis_id, "analysisId"),
                         (request.job_posting_id, "jobPostingId"), (request.workspace_id, "workspaceId"),
                         (request.profile_id, "profileId")):
        check_id(value, field)
    has_text = bool(request.input_text and request.input_text.strip())
    if not request.document_id and not has_text:
        raise invalid_input("첨삭할 문서나 글을 넣어 주세요.", missingInputs=["documentId", "inputText"])
    if request.max_characters and request.max_characters > cfg.max_characters_limit:
        raise invalid_input("글자 수 제한 값을 확인해 주세요.", field="maxCharacters", max=cfg.max_characters_limit)
    if request.question_text and len(request.question_text) > cfg.question_max_chars:
        raise invalid_input("문항이 너무 길어요.", field="questionText", maxChars=cfg.question_max_chars)
    story_ids = list(dict.fromkeys(request.story_ids))
    if len(story_ids) > cfg.max_stories:
        raise invalid_input("경험 블록은 최대 개수까지만 고를 수 있어요.", field="storyIds", max=cfg.max_stories)

    document_version = None
    text = None
    if request.document_id:
        latest = deps.users.get_document_latest(user_id, request.document_id)
        if latest is None or latest.owner_user_id != user_id:
            raise document_not_found()
        version = deps.users.get_document_version(user_id, request.document_id, latest.latest_version)
        if version is None or not version.text_key:
            raise precondition_not_met("문서 글자를 읽은 뒤에 첨삭할 수 있어요. 잠시 후 다시 시도해 주세요.")
        document_version = version.version
    else:
        text = deps.text.normalize(request.input_text)
        if not cfg.text_min_chars <= len(text) <= cfg.text_max_chars:
            raise invalid_input(f"첨삭할 글은 {cfg.text_min_chars}자 이상 {cfg.text_max_chars:,}자 이하로 넣어 주세요.",
                                field="inputText", minChars=cfg.text_min_chars, maxChars=cfg.text_max_chars)
    for story_id in story_ids:  # 다른 사용자의 경험 블록이면 404 (Requirement 9 기준 4)
        check_id(story_id, "storyIds")
        if deps.stories is None or deps.stories.get_latest(user_id, story_id) is None:
            raise not_found("경험 블록을 찾을 수 없어요.")
    if request.analysis_id:
        if deps.analyses is None:
            raise not_implemented()
        analysis = deps.analyses.get_analysis(user_id, request.analysis_id)
        if analysis is None or analysis.owner_user_id != user_id:
            raise not_found("분석 결과를 찾을 수 없어요.")
    elif request.job_posting_id:
        if deps.catalog is None:
            raise not_implemented()
        if deps.catalog.get_latest(request.job_posting_id) is None:
            raise not_found("공고를 찾을 수 없어요.")
    profile = None
    if request.profile_id:
        from mentoring.fit.analysis import _load_profile

        profile = _load_profile(deps, user_id, request.profile_id, None)

    payload = {**request.model_dump(by_alias=True, mode="json", exclude={"input_text"}),
               "inputText": text, "storyIds": story_ids, "documentVersion": document_version}

    def create() -> dict:
        now = deps.now_iso()
        review_id = deps.new_id("review")
        task_id = f"task-{review_id}"
        input_key = None
        if text is not None:  # M-12: 직접 넣은 글은 첨삭 결과와 같은 곳(S3)에만 둔다
            input_key = _key(deps, user_id, review_id, "input.txt")
            deps.objects.put_text(input_key, text)
        record = ReviewRecord(
            review_id=review_id, owner_user_id=user_id, status=TaskStatus.PENDING, task_id=task_id,
            document_type=request.document_type, document_id=request.document_id,
            document_version=document_version, input_key=input_key, analysis_id=request.analysis_id,
            job_posting_id=request.job_posting_id, workspace_id=request.workspace_id,
            profile_id=profile.profile_id if profile else None,
            profile_version=profile.profile_version if profile else None,
            question_text=request.question_text, max_characters=request.max_characters, story_ids=story_ids,
            created_at=now, updated_at=now)
        task = Task(task_id=task_id, task_type=TaskType.REVIEW, status=TaskStatus.PENDING, owner_user_id=user_id,
                    resource_id=review_id, resource_version=1, created_at=now, updated_at=now)
        store.create(result_item(PREFIX, ENTITY, record, review_id))
        deps.users.create_task(task)
        deps.tasks.dispatch(tasks.build_message(task))
        log_event("review.requested", userHash=user_hash(deps, user_id), taskId=task_id, feature=FEATURE)
        return {"reviewId": review_id, "taskId": task_id, "status": TaskStatus.PENDING.value}

    return run_idempotent(deps, user_id, idempotency_key, payload, create)


# ---------------------------------------------------------------- 실행 (작업 REVIEW)
def _get_record(deps, user_id: str, review_id: str) -> ReviewRecord | None:
    item = _store(deps).get(user_id, f"{PREFIX}#{review_id}")
    return ReviewRecord.model_validate(item) if item else None


def _save(deps, record: ReviewRecord, **changes) -> ReviewRecord:
    updated = record.model_copy(update={**changes, "updated_at": deps.now_iso()})
    _store(deps).save(result_item(PREFIX, ENTITY, updated, updated.review_id))
    return updated


def mark_failed(deps, task: Task, code: str) -> None:
    if deps.results is None:
        return
    record = _get_record(deps, task.owner_user_id, task.resource_id)
    if record is not None:
        _save(deps, record, status=TaskStatus.FAILED, error_code=code, completed_at=deps.now_iso())


def _source_text(deps, record: ReviewRecord) -> str:
    if record.input_key:
        text = deps.objects.get_text(record.input_key)
    else:
        version = deps.users.get_document_version(record.owner_user_id, record.document_id, record.document_version)
        text = deps.objects.get_text(version.text_key) if version and version.text_key else None
    if not text:
        raise MentoringError(500, "INTERNAL_ERROR", "첨삭할 글을 찾을 수 없어요.", True)
    return text


def _posting_basis(deps, record: ReviewRecord) -> tuple[PostingBasis, list[dict]]:
    uid = record.owner_user_id
    if record.analysis_id and deps.analyses is not None:
        analysis = deps.analyses.get_analysis(uid, record.analysis_id)
        if analysis is not None and analysis.requirements:
            reqs = [{"name": r.name, "kind": r.category, **({"sourceQuote": r.source_quote} if r.source_quote else {})}
                    for r in analysis.requirements]
            return PostingBasis(mode="POSTING", job_posting_id=analysis.job_posting_id,
                                snapshot_id=analysis.snapshot_id, analysis_id=analysis.analysis_id,
                                requirement_names=[r.name for r in analysis.requirements]), reqs
    if record.job_posting_id and deps.catalog is not None:
        raw_latest = deps.catalog.get_latest(record.job_posting_id)
        if raw_latest:
            latest = PostingLatestView.model_validate(raw_latest)
            raw = deps.catalog.get_snapshot(latest.job_posting_id, latest.snapshot_id)
            if raw:
                posting = PostingSnapshotView.model_validate(raw)
                reqs = [{"name": r.name, "kind": r.kind, **({"sourceQuote": r.source_quote} if r.source_quote else {})}
                        for r in posting.requirements]
                return PostingBasis(mode="POSTING", job_posting_id=posting.job_posting_id,
                                    snapshot_id=posting.snapshot_id,
                                    requirement_names=[r.name for r in posting.requirements]), reqs
    return PostingBasis(mode="GENERAL"), []


def _confirmed_facts(deps, record: ReviewRecord) -> tuple[list[dict], list[str]]:
    """(모델에 넘길 경험 블록, 사실 검사 근거 문장). 사용자가 확인한 것만 쓴다 (Requirement 9 기준 4)."""
    from mentoring.stories.service import story_for_review

    uid = record.owner_user_id
    stories, corpus = [], []
    for story_id in record.story_ids:
        if deps.stories is None:
            break
        try:
            story = story_for_review(deps, deps.stories, uid, story_id)
        except MentoringError:
            continue
        stories.append(story)
        for field in _STAR:
            value = story.get(field)
            corpus.extend(value if isinstance(value, list) else [value] if value else [])
    pointer = deps.users.get_profile_pointer(uid)
    if pointer is not None:
        profile = deps.users.get_profile_version(uid, record.profile_id or pointer.latest_profile_id,
                                                 record.profile_version or pointer.latest_version)
        if profile is not None:
            evidence = {e.evidence_id: e.quoted_text for e in profile.evidence}
            for skill in profile.skills:
                if skill.fact_status == FactStatus.VERIFIED:
                    corpus.append(skill.name)
                    corpus.extend(evidence[i] for i in skill.evidence_ids if i in evidence)
            corpus.extend(c.name for c in profile.certificates if c.fact_status == FactStatus.VERIFIED)
    return stories, corpus


def run_review(deps, task: Task) -> ReviewOutcome:
    started = time.perf_counter()
    cfg = deps.config.review
    uid = task.owner_user_id
    record = _get_record(deps, uid, task.resource_id)
    if record is None or record.owner_user_id != uid:
        raise not_found()
    record = _save(deps, record, status=TaskStatus.PROCESSING)

    text = _source_text(deps, record)
    char_count = count_chars(text, record.max_characters)
    basis, requirements = _posting_basis(deps, record)
    stories, corpus = _confirmed_facts(deps, record)
    masked = deps.text.mask_pii(text)
    if len(masked.masked_text) != len(text):
        raise MentoringError(500, "INTERNAL_ERROR", "개인정보 가리기 결과가 올바르지 않아요.", False)
    safe_text = masked.masked_text
    question = deps.text.mask_pii(record.question_text).masked_text if record.question_text else None
    stories_view = [{k: (deps.text.mask_pii(v).masked_text if isinstance(v, str) else v) for k, v in s.items()}
                    for s in stories]

    def on_failure(calls):
        emit_metric(deps, "LLMSchemaFailure", 1, feature=FEATURE)
        log_event("review.validation", userHash=user_hash(deps, uid), taskId=task.task_id, feature=FEATURE,
                  validation="SCHEMA_INVALID", retryCount=calls - 1)

    output, calls = call_structured(
        deps, REVIEW_SYSTEM,
        lambda problems: build_review_user(text=safe_text, question=question, requirements=requirements,
                                           stories=stories_view, intents=cfg.intents, issue_types=cfg.issue_types,
                                           max_characters=record.max_characters, problems=problems),
        ReviewOutput, max_tokens=cfg.max_tokens, retries=cfg.schema_retries, on_schema_failure=on_failure)

    allowed_corpus = "\n".join([text, *corpus])
    issues, dropped, rejected = _validate_issues(deps, output, safe_text, allowed_corpus, set(record.story_ids))
    issues = _add_blind_risks(deps, safe_text, issues)
    warnings = [_warn("DRAFT_NOTICE")]
    if basis.mode == "GENERAL":
        warnings.append(_warn("NOT_POSTING_SPECIFIC"))
    if char_count.over_limit:
        warnings.append(_warn("LENGTH_OVER"))
    if rejected:
        warnings.append(_warn("FACT_CHECK"))
        emit_metric(deps, "FactCheckRejected", rejected, feature=FEATURE)
    if dropped:
        emit_metric(deps, "EvidenceValidationFailure", dropped, feature=FEATURE)

    feedback = _clean_sentence(deps, allowed_corpus, output.overall_feedback) or "첨삭 결과를 아래 항목에서 확인해 주세요."
    strengths = [s for s in (_clean_sentence(deps, allowed_corpus, x) for x in output.strengths) if s]
    missing = [q.strip() for q in output.missing_questions if q.strip()][:cfg.max_questions]
    needs_confirmation = rejected > 0 or any(i.needs_user_confirmation for i in issues) or bool(missing)
    intent = output.question_intent if output.question_intent in cfg.intents else "OTHER"
    body = ReviewBody(
        review_id=record.review_id, question_intent=intent, overall_feedback=feedback, strengths=strengths,
        issues=issues, missing_questions=missing, char_count=char_count, posting_basis=basis,
        used_story_ids=sorted({s for i in issues for s in i.used_story_ids}),
        fact_check_status="NEEDS_CONFIRMATION" if needs_confirmation else "PASSED", warnings=warnings,
        model_id=getattr(deps.llm, "model_id", None), prompt_version=cfg.prompt_version)
    result_key = _key(deps, uid, record.review_id, "result.json")
    deps.objects.put_text(result_key, body.model_dump_json(by_alias=True, exclude_none=True))

    all_dropped = bool(output.issues) and not issues
    status = TaskStatus.REQUIRES_USER_REVIEW if all_dropped else TaskStatus.COMPLETED
    reason = REVIEW_SPAN_MISMATCH if all_dropped else None
    _save(deps, record, status=status, review_reason=reason, result_key=result_key, issue_count=len(issues),
          fact_check_status=body.fact_check_status, used_story_ids=body.used_story_ids,
          source_job_snapshot_id=basis.snapshot_id, model_id=body.model_id, prompt_version=body.prompt_version,
          completed_at=deps.now_iso())
    emit_metric(deps, "AnalysisLatency", round((time.perf_counter() - started) * 1000, 1), feature=FEATURE)
    log_event("review.completed", userHash=user_hash(deps, uid), taskId=task.task_id, feature=FEATURE,
              status=status.value, modelId=body.model_id, promptVersion=body.prompt_version, retryCount=calls - 1,
              counts={"issues": len(issues), "droppedSpans": dropped, "factRejected": rejected,
                      "chars": char_count.with_spaces})
    return ReviewOutcome(status, record.review_id, reason, calls - 1)


def _clean_sentence(deps, corpus: str, text: str | None) -> str | None:
    """모델 설명 문장에 원문에 없는 숫자·기간·날짜가 있으면 그 문장을 쓰지 않는다."""
    text = (text or "").strip()
    if not text or deps.text.find_unsupported_facts(corpus, text):
        return None
    return text


def _validate_issues(deps, output: ReviewOutput, safe_text: str, corpus: str, story_ids: set[str]):
    cfg = deps.config.review
    issues: list[ReviewIssue] = []
    dropped = rejected = 0
    for item in output.issues:
        if len(issues) >= cfg.max_issues:
            break
        check = deps.text.check_evidence(safe_text, item.original_text, item.start_char, item.end_char)
        status = str(getattr(getattr(check, "status", None), "value", getattr(check, "status", None)))
        if status not in _FOUND or not safe_text[check.start:check.end].strip():
            dropped += 1  # 원문에 없는 구간은 저장하지 않는다 (Requirement 10 기준 2)
            continue
        issue_type = item.issue_type if item.issue_type in cfg.issue_types else "OTHER"
        questions = [q.strip() for q in item.questions if q.strip()][:cfg.max_questions]
        revised = (item.revised_example or "").strip() or None
        fact_check = "NOT_APPLICABLE"
        needs = False
        if revised:
            unsupported = deps.text.find_unsupported_facts(corpus, revised)
            if unsupported:  # 없는 사실이 들어간 예시는 빼고 묻는다 (Requirement 10 기준 4, UT-14)
                rejected += 1
                revised, fact_check, needs = None, "REJECTED", True
                questions.append("수정 예시에 넣을 숫자·기간·날짜가 있다면 실제 값을 알려 주세요.")
            else:
                fact_check = "PASSED"
        if questions:
            needs = True
        issues.append(ReviewIssue(
            issue_id=f"issue-{len(issues) + 1}", source_span=SourceSpan(start_char=check.start, end_char=check.end),
            original_text=safe_text[check.start:check.end], issue_type=issue_type, reason=item.reason.strip(),
            improvement_action=item.improvement_action.strip(), revised_example=revised,
            needs_user_confirmation=needs, questions=questions[:cfg.max_questions],
            used_story_ids=[s for s in item.used_story_ids if s in story_ids], fact_check=fact_check))
    return issues, dropped, rejected


def _add_blind_risks(deps, safe_text: str, issues: list[ReviewIssue]) -> list[ReviewIssue]:
    """직무와 무관한 개인정보 표현을 규칙으로 한 번 더 찾는다. 모델이 이미 알린 구간은 겹쳐 넣지 않는다."""
    taken = [(i.source_span.start_char, i.source_span.end_char) for i in issues if i.issue_type == "BLIND_RISK"]
    result = list(issues)
    for pattern in deps.config.review.blind_risk_patterns:
        for match in re.finditer(pattern, safe_text):
            start, end = match.start(), match.end()
            if any(s < end and start < e for s, e in taken):
                continue
            taken.append((start, end))
            result.append(ReviewIssue(
                issue_id=f"issue-{len(result) + 1}", source_span=SourceSpan(start_char=start, end_char=end),
                original_text=safe_text[start:end], issue_type="BLIND_RISK",
                reason="직무와 관계없는 개인정보라 블라인드 채용에서 문제가 될 수 있어요.",
                improvement_action="지원 공고의 블라인드 기준을 확인하고 이 표현을 빼거나 바꿔 주세요.",
                detected_by="RULE"))
    return result


# ---------------------------------------------------------------- 조회 (GET /reviews/{id})
def get_review(deps, user_id: str, review_id: str) -> dict:
    check_id(review_id, "reviewId")
    record = _get_record(deps, user_id, review_id)
    if record is None or record.owner_user_id != user_id:
        raise not_found()
    view = {k: v for k, v in record.to_api().items() if k not in ("ownerUserId", "inputKey", "resultKey")}
    if record.status in (TaskStatus.COMPLETED, TaskStatus.REQUIRES_USER_REVIEW) and record.result_key:
        raw = deps.objects.get_text(record.result_key)
        if raw:
            body = ReviewBody.model_validate_json(raw)
            view.update(body.to_api())
    return view
