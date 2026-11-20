"""보강 배치 입구.

담당 워크트리: enrich. 명세: 개발계획서2 §4.2 B-02. 테스트: T-18.
"""

from datetime import date, datetime

from ..core import clock
from ..deps import Deps
from ..models.enums import ExtractStatus
from ..models.posting import PostingLatest, PostingSnapshot, latest_from_snapshot
from .badges import build_badges, find_company
from .embed import embed_posting
from .extract import KEEP_OWNERS, extract_requirements, source_text
from .precompute_alternatives import precompute_alternatives
from .regional_talent import judge_regional_talent


def _is_expired(existing: PostingLatest | None, snapshot: PostingSnapshot, as_of: datetime) -> bool:
    """한 번 마감으로 바뀐 공고는 그대로 둔다. 아니면 as_of로 다시 본다."""
    return bool(existing and existing.is_expired) or clock.is_expired(snapshot.closes_at, as_of)


def _alt_bases(deps: Deps, done_ids: list[str], as_of: datetime) -> list[str]:
    """대안 후보를 다시 계산할 수도권 공고. 부산 공고가 바뀌었으면 진행 중인 수도권 공고 전부를 다시 본다."""
    bases = list(done_ids)
    changed = deps.catalog.batch_get_latest(done_ids)
    if any(latest.is_busan for latest in changed.values()):
        for sido in deps.config.data.capital_area_sido:
            for latest in deps.catalog.query_postings_by_sido(sido, closes_from=clock.day(as_of)):
                bases.append(latest.job_posting_id)
    return list(dict.fromkeys(bases))


def enrich_one(deps: Deps, snapshot: PostingSnapshot, as_of: datetime, *,
               raw_text: str | None = None) -> PostingSnapshot:
    """스냅샷 하나를 보강한다. 저장은 하지 않는다."""
    if deps.llm is not None and snapshot.extract_status != ExtractStatus.DONE:
        snapshot = extract_requirements(deps, snapshot, raw_text=raw_text).snapshot
    company = find_company(deps, snapshot)
    update: dict = {"badges": build_badges(deps, snapshot, company)}
    if snapshot.extracted_by.get("regionalTalent") not in KEEP_OWNERS:
        update["regional_talent"] = judge_regional_talent(company, source_text(snapshot, raw_text))
    if company is not None and not snapshot.company_id:
        update["company_id"] = company.company_id
    return snapshot.model_copy(update=update)


def enrich_postings(deps: Deps, job_posting_ids: list[str], *,
                    as_of: str | date | datetime | None = None,
                    raw_texts: dict[str, str] | None = None) -> dict:
    """요건 추출, 임베딩, 배지, 지역인재, 부산 대안 후보 계산을 차례로 한다.

    API에서 받은 값(마감일·근무지·급여)은 LLM 결과로 덮어쓰지 않는다. 한 번 다시 시도해도 추출에 실패하면
    extractStatus=FAILED로 둔다. 돌려주는 값은 건수 요약 {"enriched", "failed", "alts"}.
    raw_texts는 jobPostingId별 공고 원문이다. 없으면 제목과 업무 설명만 쓴다.
    LLM이 없으면(deps.llm is None) 추출은 건너뛰고 나머지만 한다.
    """
    now = clock.parse_as_of(as_of)
    raw_texts = raw_texts or {}
    busan, capital = deps.config.data.busan_sido, deps.config.data.capital_area_sido
    enriched = failed = 0
    done_ids: list[str] = []
    for job_posting_id in dict.fromkeys(job_posting_ids):  # 순서를 지키며 중복을 뺀다
        existing = deps.catalog.get_latest(job_posting_id)
        if existing is None:
            continue
        snapshot = deps.catalog.get_snapshot(job_posting_id, existing.snapshot_id)
        if snapshot is None:
            continue
        snapshot = enrich_one(deps, snapshot, now, raw_text=raw_texts.get(job_posting_id))
        latest = latest_from_snapshot(snapshot, busan_sido=busan, capital_sido=capital,
                                      is_expired=_is_expired(existing, snapshot, now))
        latest = latest.model_copy(update={"is_sample": latest.is_sample or existing.is_sample})
        deps.catalog.put_snapshot(snapshot)
        deps.catalog.put_latest(latest)
        embed_posting(deps, snapshot, latest)
        enriched += 1
        failed += snapshot.extract_status == ExtractStatus.FAILED
        done_ids.append(job_posting_id)
    alts = precompute_alternatives(deps, _alt_bases(deps, done_ids, now), now)
    return {"enriched": enriched, "failed": int(failed), "alts": alts}

