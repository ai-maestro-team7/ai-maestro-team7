"""원문 근거가 붙은 역량 추출 (Requirement 6, 7 기준 1·2, 개발계획서1 F-01 처리 7~11단계).

순서는 고정이다. 모델 판단에 맡기지 않는다 (A §3.1, §10.2):
  텍스트 읽기 → 개인정보 가리기 → 모델 호출 → 형식 검사(재시도) → 근거·사실 검증(재요청) → 프로필 새 버전 저장

지키는 것
- 근거 인용은 원문(정규화 텍스트)에 실제로 있어야 한다. 없으면 근거로 저장하지 않는다 (A §4.3)
- 근거가 하나도 남지 않은 역량은 프로필에 넣지 않고 needsConfirmation으로 돌린다. 부족으로 확정하지 않는다 (A §4.2)
- 원문에 없는 수치·날짜·기간·자격을 쓴 항목은 한 번 고쳐 달라고 하고, 그래도 남으면 빼고 REQUIRES_USER_REVIEW (A F-01 10단계)
- 모델이 고른 확인 상태는 쓰지 않는다. 사용자 확인 전의 역량은 모두 NEEDS_CONFIRMATION이다 (Requirement 6 기준 8)
"""
import bisect
import json
import re
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from ..errors import MentoringError, aws_service_error, document_not_found
from ..llm.prompts import PROFILE_EXTRACT_SYSTEM, build_profile_extract_user
from ..models import (
    CareerProfile,
    Certificate,
    DocumentVersion,
    Evidence,
    EvidenceLevel,
    ExtractionStatus,
    FactStatus,
    ProfileEntry,
    Skill,
    Task,
    TaskStatus,
)
from ..models.llm_output import ExtractedEntry, ExtractionOutput, QuoteRef
from ..ports import VersionConflict
from .documents import set_document_status
from .logs import log_event, user_hash
from .metrics import emit_metric
from .taxonomy import Taxonomy, load_taxonomy, taxonomy_for_prompt

REVIEW_EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
_FOUND = {"EXACT", "RELOCATED"}


@dataclass
class ExtractionOutcome:
    status: TaskStatus
    result_id: str
    review_reason: str | None
    retry_count: int


@dataclass
class Assembled:
    skills: list[Skill] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    projects: list[ProfileEntry] = field(default_factory=list)
    experiences: list[ProfileEntry] = field(default_factory=list)
    certificates: list[Certificate] = field(default_factory=list)
    needs_confirmation: list[str] = field(default_factory=list)
    unsupported_values: list[str] = field(default_factory=list)  # 재요청 때 모델에 알려 줄 값 (로그에는 남기지 않는다)
    unsupported_items: int = 0
    dropped_without_evidence: int = 0


# ---------------------------------------------------------------- 실행
def run_profile_extraction(deps, task: Task) -> ExtractionOutcome:
    started = time.perf_counter()
    uid = task.owner_user_id
    version = deps.users.get_document_version(uid, task.resource_id, task.resource_version)
    if version is None or version.owner_user_id != uid:  # 작업을 처리할 때 소유권을 다시 확인한다 (A §10.1)
        raise document_not_found()
    source = deps.objects.get_text(version.text_key) if version.text_key else None
    if source is None:
        raise MentoringError(500, "INTERNAL_ERROR", "문서 텍스트를 찾을 수 없어요.", True)
    set_document_status(deps, uid, version.document_id, version.version, ExtractionStatus.ANALYZING)

    masked = deps.text.mask_pii(source)
    if len(masked.masked_text) != len(source):  # 위치가 어긋나면 근거 검증이 무너진다
        raise MentoringError(500, "INTERNAL_ERROR", "개인정보 가리기 결과가 올바르지 않아요.", False)

    cfg = deps.config.extraction
    taxonomy = load_taxonomy(deps, uid)
    taxonomy_view = taxonomy_for_prompt(taxonomy)
    problems: list[str] | None = None
    schema_failures = fact_retries = calls = 0
    while True:
        calls += 1
        try:
            raw = deps.llm.invoke(PROFILE_EXTRACT_SYSTEM,
                                  build_profile_extract_user(masked.masked_text, problems, taxonomy_view),
                                  max_tokens=cfg.max_tokens)
        except MentoringError:
            raise
        except Exception:  # noqa: BLE001 - Bedrock 오류 종류와 관계없이 다시 시도할 수 있는 오류로 남긴다
            raise aws_service_error("bedrock") from None
        output = parse_output(raw)
        if output is None:
            schema_failures += 1
            _log_validation(deps, task, "SCHEMA_INVALID", calls)
            emit_metric(deps, "LLMSchemaFailure", 1, feature="profile")
            if schema_failures > cfg.schema_retries:
                raise MentoringError(500, "AI_OUTPUT_INVALID",
                                     "분석 결과 형식이 올바르지 않아요. 잠시 후 다시 시도해 주세요.", True)
            problems = ["출력이 정해진 JSON 형식과 맞지 않았다"]
            continue
        assembled = assemble(deps, source, version, masked.spans, output, taxonomy)
        if assembled.unsupported_items and fact_retries < cfg.fact_retries:
            fact_retries += 1
            _log_validation(deps, task, "UNSUPPORTED_FACTS", calls)
            values = ", ".join(sorted(set(assembled.unsupported_values))[:10])
            problems = [f"원문에 없는 내용을 썼다: {values}. 원문에 적힌 것만 쓴다"]
            continue
        break

    profile = _save_profile(deps, uid, version, assembled)
    if assembled.unsupported_items:
        status, doc_status, reason = (TaskStatus.REQUIRES_USER_REVIEW, ExtractionStatus.REQUIRES_USER_REVIEW,
                                      REVIEW_EVIDENCE_MISMATCH)
    else:
        status, doc_status, reason = TaskStatus.COMPLETED, ExtractionStatus.COMPLETED, None
    set_document_status(deps, uid, version.document_id, version.version, doc_status, review_reason=reason)
    failed_checks = assembled.unsupported_items + assembled.dropped_without_evidence
    if failed_checks:
        emit_metric(deps, "EvidenceValidationFailure", failed_checks, feature="profile")
    emit_metric(deps, "AnalysisLatency", round((time.perf_counter() - started) * 1000, 1), feature="profile")
    log_event("profile.extracted", userHash=user_hash(deps, uid), taskId=task.task_id, feature="profile",
              status=status.value, modelId=deps.llm.model_id, promptVersion=cfg.prompt_version,
              validation="PASS" if not assembled.unsupported_items else REVIEW_EVIDENCE_MISMATCH,
              retryCount=calls - 1,
              counts={"skills": len(assembled.skills), "evidence": len(assembled.evidence),
                      "droppedWithoutEvidence": assembled.dropped_without_evidence,
                      "unsupportedItems": assembled.unsupported_items})
    return ExtractionOutcome(status=status, result_id=f"{profile.profile_id}-v{profile.profile_version}",
                             review_reason=reason, retry_count=calls - 1)


def _log_validation(deps, task: Task, validation: str, calls: int) -> None:
    log_event("profile.validation", userHash=user_hash(deps, task.owner_user_id), taskId=task.task_id,
              feature="profile", validation=validation, retryCount=calls - 1, modelId=deps.llm.model_id)


# ---------------------------------------------------------------- 모델 출력 읽기
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_output(raw: str) -> ExtractionOutput | None:
    """고정 스키마로 읽는다. 형식이 맞지 않으면 None (호출한 쪽이 재시도 여부를 정한다)."""
    if not isinstance(raw, str):
        return None
    text = _FENCE.sub("", raw.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start:end + 1])
        return ExtractionOutput.model_validate(data)
    except (ValueError, ValidationError):
        return None


# ---------------------------------------------------------------- 검증과 조립
def _status_of(check) -> str:
    status = getattr(check, "status", None)
    return str(getattr(status, "value", status))


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def _page(start: int, page_starts: list[int]) -> int:
    if not page_starts:
        return 1
    return max(1, bisect.bisect_right(page_starts, start))


def assemble(deps, source: str, version: DocumentVersion, mask_spans: list, output: ExtractionOutput,
             taxonomy: Taxonomy | None = None) -> Assembled:
    result = Assembled()
    unit_codes = taxonomy.unit_codes if taxonomy else set()
    basic_ids = taxonomy.basic_ids if taxonomy else set()
    evidence_ids_by_span: dict[tuple[int, int], str] = {}
    compact_source = _compact(source)

    def evidence_for(quotes: list[QuoteRef]) -> list[str]:
        ids: list[str] = []
        for quote in quotes:
            check = deps.text.check_evidence(source, quote.quoted_text, quote.start_char, quote.end_char)
            if _status_of(check) not in _FOUND:
                continue
            start, end = check.start, check.end
            if deps.text.overlaps_mask(start, end, mask_spans):  # 가린 개인정보는 근거로 쓰지 않는다
                continue
            key = (start, end)
            if key not in evidence_ids_by_span:
                evidence_id = f"ev-{len(result.evidence) + 1}"
                result.evidence.append(Evidence(
                    evidence_id=evidence_id, source_document_id=version.document_id,
                    page=_page(start, version.page_starts), start_char=start, end_char=end,
                    quoted_text=source[start:end]))
                evidence_ids_by_span[key] = evidence_id
            if evidence_ids_by_span[key] not in ids:
                ids.append(evidence_ids_by_span[key])
        return ids

    def unsupported(*texts: str | None) -> list[str]:
        joined = " ".join(t for t in texts if t)
        if not joined:
            return []
        return [str(getattr(f, "value", f)) for f in deps.text.find_unsupported_facts(source, joined)]

    def reject(values: list[str]) -> None:
        result.unsupported_values.extend(values)
        result.unsupported_items += 1

    def need(text: str) -> None:
        text = text.strip()
        if text and text not in result.needs_confirmation:
            result.needs_confirmation.append(text)

    # 역량
    skills_by_name: dict[str, Skill] = {}
    for item in output.skills:
        name = item.name.strip()
        if item.evidence_level == EvidenceLevel.USER_CONFIRMED_GAP:  # 사용자만 정할 수 있다
            continue
        if item.evidence_level == EvidenceLevel.NOT_FOUND:  # 서류에 없음 = 미확인. 먼저 묻는다
            need(name)
            continue
        bad = unsupported(name, item.normalized_name)
        if bad:
            reject(bad)
            continue
        ids = evidence_for(item.quotes)
        if not ids:
            result.dropped_without_evidence += 1
            need(name)
            continue
        existing = skills_by_name.get(name.lower())
        if existing is not None:
            existing.evidence_ids.extend(i for i in ids if i not in existing.evidence_ids)
            continue
        code = (item.ncs_unit_code or "").strip() or None
        if code and taxonomy is not None:
            code = code if code in unit_codes else None  # 넘긴 후보 목록에 있는 코드만 (#104)
        elif code and (deps.reference is None or deps.reference.get_competency_unit(code) is None):
            code = None  # 기준 데이터에 없는 코드는 넣지 않는다 (Requirement 6 기준 10)
        basic_id = (item.basic_skill_id or "").strip() or None
        if basic_id not in basic_ids:
            basic_id = None
        skill = Skill(skill_id=f"skill-{len(result.skills) + 1}", name=name,
                      normalized_name=(item.normalized_name or "").strip() or None, ncs_unit_code=code,
                      basic_skill_id=basic_id, evidence_level=item.evidence_level,
                      fact_status=FactStatus.NEEDS_CONFIRMATION, evidence_ids=ids)
        result.skills.append(skill)
        skills_by_name[name.lower()] = skill

    # 프로젝트·경험
    def entries(items: list[ExtractedEntry], prefix: str, target: list[ProfileEntry]) -> None:
        for item in items:
            bad = unsupported(item.name, item.summary, item.period)
            if bad:
                reject(bad)
                continue
            ids = evidence_for(item.quotes)
            if not ids:
                result.dropped_without_evidence += 1
                continue
            target.append(ProfileEntry(item_id=f"{prefix}-{len(target) + 1}", name=item.name.strip(),
                                       summary=(item.summary or "").strip() or None,
                                       period=(item.period or "").strip() or None,
                                       fact_status=FactStatus.NEEDS_CONFIRMATION, evidence_ids=ids))

    entries(output.projects, "proj", result.projects)
    entries(output.experiences, "exp", result.experiences)

    # 자격: 이름이 원문에 있어야 한다. 없는 자격을 만들지 않는다
    for item in output.certificates:
        name = item.name.strip()
        bad = unsupported(name)
        if _compact(name) not in compact_source:
            bad.append(name)
        if bad:
            reject(bad)
            continue
        ids = evidence_for(item.quotes) or evidence_for([QuoteRef(quoted_text=name)])
        if not ids:
            result.dropped_without_evidence += 1
            continue
        result.certificates.append(Certificate(item_id=f"cert-{len(result.certificates) + 1}", name=name,
                                               fact_status=FactStatus.NEEDS_CONFIRMATION, evidence_ids=ids))

    for text in output.needs_confirmation:
        if not unsupported(text):  # 확인 질문에도 지어낸 수치를 넣지 않는다
            need(text)
    return result


# ---------------------------------------------------------------- 저장
def _save_profile(deps, user_id: str, version: DocumentVersion, assembled: Assembled) -> CareerProfile:
    for attempt in range(2):
        pointer = deps.users.get_profile_pointer(user_id)
        previous = (deps.users.get_profile_version(user_id, pointer.latest_profile_id, pointer.latest_version)
                    if pointer else None)
        profile = CareerProfile(
            profile_id=pointer.latest_profile_id if pointer else deps.new_id("profile"),
            profile_version=(pointer.latest_version + 1) if pointer else 1,
            based_on_version=pointer.latest_version if pointer else None,
            owner_user_id=user_id, created_by="EXTRACTION", source_document_ids=[version.document_id],
            target_role_preference=list(previous.target_role_preference) if previous else [],
            skills=assembled.skills, evidence=assembled.evidence, projects=assembled.projects,
            experiences=assembled.experiences, certificates=assembled.certificates,
            needs_confirmation=assembled.needs_confirmation, model_id=deps.llm.model_id,
            prompt_version=deps.config.extraction.prompt_version, created_at=deps.now_iso())
        try:
            deps.users.put_profile_version(profile, expected_version=pointer.latest_version if pointer else None)
            return profile
        except VersionConflict:
            if attempt == 1:
                raise MentoringError(409, "PRECONDITION_NOT_MET", "프로필이 동시에 바뀌었어요. 다시 시도해 주세요.",
                                     True) from None
    raise AssertionError("unreachable")
