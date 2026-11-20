"""수집 배치 입구.

담당 워크트리: ingest. 명세: 개발계획서2 §4.2 B-01, §3. 테스트: T-17.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from ..config import OpportunityConfig
from ..core import clock
from ..core.facts import is_relocated
from ..enrich.extract import KEEP_OWNERS
from ..enrich.regional_talent import judge_posting_regional_talent
from ..models.enums import ExtractStatus, PolicySource, RegionalTalentStatus
from ..models.policy import ALWAYS_APPLY_END, Policy
from ..models.posting import CompanyRecord, PostingLatest, PostingSnapshot, latest_from_snapshot
from ..ports import CatalogRepo

# 마감 처리 때 지난 며칠까지 거슬러 읽을지, 시·도마다 몇 건까지 읽을지. 설정 파일에 자리가 생기면 옮긴다.
EXPIRE_LOOKBACK_DAYS = 14
EXPIRE_QUERY_LIMIT = 1000


def has_regional_conditions(latest: PostingLatest | None) -> bool:
    """지역 조건 색인에 둘 공고인지. 진행 중이고 공고문에서 지역 조건을 찾은(LIKELY) 공고."""
    talent = latest.regional_talent if latest else None
    return bool(latest and not latest.is_expired and talent and talent.status == RegionalTalentStatus.LIKELY)


def sync_regional_index(catalog: CatalogRepo, before: PostingLatest | None, after: PostingLatest) -> None:
    """LATEST를 쓴 뒤 지역 조건 색인을 맞춘다. 조건이 있으면 넣고(마감일 갱신), 없어졌거나 마감되면 지운다."""
    if has_regional_conditions(after):
        catalog.put_regional_index(after)
    elif has_regional_conditions(before):
        catalog.delete_regional_index(after.job_posting_id)


def rejudge_regional_talent(config: OpportunityConfig, snapshot: PostingSnapshot) -> PostingSnapshot:
    """공고문의 지역 조건을 지금 규칙으로 다시 읽는다. 내용이 같아도 규칙이 바뀌면 값이 바뀐다.

    부산 이전기관인지는 이전 보강에서 붙인 배지로 안다. 사람이 넣은 값(API·MANUAL)은 그대로 둔다.
    값이 같으면 같은 객체를 돌려준다.
    """
    if snapshot.extracted_by.get("regionalTalent") in KEEP_OWNERS:
        return snapshot
    text = "\n".join(x for x in (snapshot.title, snapshot.job_description or "") if x)
    talent = judge_posting_regional_talent(config, snapshot, text, relocated=is_relocated(snapshot.badges))
    if talent == snapshot.regional_talent:
        return snapshot
    return snapshot.model_copy(update={"regional_talent": talent})


def upsert_postings(config: OpportunityConfig, catalog: CatalogRepo, snapshots: list[PostingSnapshot], *,
                    as_of: str | date | datetime | None = None) -> dict:
    """정규화한 공고를 넣는다. contentHash가 바뀐 공고만 새 SNAP#을 쓰고 LATEST를 바꾼다.

    같은 날 두 번 돌려도 건수가 같다 (T-17). 돌려주는 값: {"created", "updated", "unchanged", "needsEnrich": [id…]}.

    - 내용이 같으면 스냅샷을 새로 쓰지 않는다. 이미 보강된 요건·배지·지역인재는 그대로 둔다.
      LATEST에는 확인 시각(checkedAt)과 마감 여부만 갱신한다.
    - 내용이 바뀌면 새 스냅샷을 쓴다. 요건은 새 원문에서 다시 뽑아야 해서 비우고(PENDING),
      기업에서 오는 배지·지역인재·기업 연결은 이전 스냅샷 것을 이어받는다.
    """
    when = clock.parse_as_of(as_of)
    checked_at = clock.iso(when)
    result: dict = {"created": 0, "updated": 0, "unchanged": 0, "needsEnrich": []}
    for snap in snapshots:
        expired = clock.is_expired(snap.closes_at, when)
        latest = catalog.get_latest(snap.job_posting_id)
        previous = catalog.get_snapshot(snap.job_posting_id, latest.snapshot_id) if latest else None

        if previous is not None and previous.content_hash == snap.content_hash:
            judged = rejudge_regional_talent(config, previous)
            if judged is not previous:
                catalog.put_snapshot(judged)
            refreshed = latest.model_copy(update={"checked_at": checked_at, "is_expired": expired,
                                                  "regional_talent": judged.regional_talent})
            if refreshed != latest:
                catalog.put_latest(refreshed)
            sync_regional_index(catalog, latest, refreshed)
            result["unchanged"] += 1
            continue

        new = snap
        if previous is not None:
            new = snap.model_copy(update={"badges": previous.badges, "regional_talent": previous.regional_talent,
                                          "company_id": snap.company_id or previous.company_id})
        stored = catalog.get_snapshot(new.job_posting_id, new.snapshot_id)
        if stored is None:  # 같은 날 A→B→A로 돌아온 경우는 이미 있는 스냅샷(보강 결과 포함)을 다시 가리킨다
            stored = rejudge_regional_talent(config, new)
            catalog.put_snapshot(stored)
        else:
            judged = rejudge_regional_talent(config, stored)
            if judged is not stored:
                catalog.put_snapshot(judged)
                stored = judged
        written = latest_from_snapshot(stored, busan_sido=config.data.busan_sido,
                                       capital_sido=config.data.capital_area_sido, is_expired=expired)
        catalog.put_latest(written)
        sync_regional_index(catalog, latest, written)
        result["created" if latest is None else "updated"] += 1
        if stored.extract_status != ExtractStatus.DONE:
            result["needsEnrich"].append(stored.job_posting_id)
    return result


def expire_postings(config: OpportunityConfig, catalog: CatalogRepo, *,
                    as_of: str | date | datetime | None = None,
                    job_posting_ids: Sequence[str] | None = None) -> int:
    """마감이 지난 공고의 LATEST.isExpired를 true로 바꾼다. 스냅샷은 지우지 않는다. 바꾼 건수를 돌려준다.

    Scan은 쓰지 않는다. 대상은 두 곳에서 모은다.
    - 인자로 받은 ID 목록(BatchGetItem)
    - 부산·수도권 시·도(설정값)의 시·도 인덱스에서 최근 `EXPIRE_LOOKBACK_DAYS`일 안에 마감한 공고
    근무지를 모르는 공고는 시·도 인덱스에 없어서 ID 목록으로만 마감 처리된다.
    """
    when = clock.parse_as_of(as_of)
    rows = {}
    if job_posting_ids:
        rows.update(catalog.batch_get_latest(list(job_posting_ids)))
    closes_from = (when.date() - timedelta(days=EXPIRE_LOOKBACK_DAYS)).isoformat()
    for sido in [config.data.busan_sido, *config.data.capital_area_sido]:
        for row in catalog.query_postings_by_sido(sido, closes_from=closes_from, limit=EXPIRE_QUERY_LIMIT):
            rows[row.job_posting_id] = row
    changed = 0
    for row in rows.values():
        if not row.is_expired and clock.is_expired(row.closes_at, when):
            expired = row.model_copy(update={"is_expired": True})
            catalog.put_latest(expired)
            sync_regional_index(catalog, row, expired)
            changed += 1
    return changed


# ---------------------------------------------------------------- 정책
def _plain_id(value: str | None) -> str:
    return (value or "").removeprefix("ythc-").strip()


def _find_seed(catalog: CatalogRepo, policy: Policy) -> Policy | None:
    """같은 youthcenterId를 가진 직접 정리 정책(시드)을 찾는다. 전국·해당 시·도 키에서만 찾는다."""
    wanted = _plain_id(policy.youthcenter_id)
    keys = {policy.region_key(), "00", *(r.sido for r in policy.regions if r.sido)}
    for key in sorted(keys):
        for candidate in catalog.query_policies(key):
            if candidate.source != PolicySource.YOUTHCENTER and _plain_id(candidate.youthcenter_id) == wanted:
                return candidate
    return None


def _blank(value) -> bool:
    return value is None or value == "" or value == []


def _enrich_seed(seed: Policy, api: Policy) -> Policy:
    """시드에 비어 있는 칸만 온통청년 값으로 채운다. 시드에 적힌 값과 verified는 그대로 둔다."""
    update = {name: getattr(api, name)
              for name in ("summary", "amount_max", "age_min", "age_max", "residence_rule", "income_rule",
                           "apply_start", "url", "category", "regions", "benefit")
              if _blank(getattr(seed, name)) and not _blank(getattr(api, name))}
    if seed.apply_end == ALWAYS_APPLY_END and api.apply_end != ALWAYS_APPLY_END:
        update["apply_end"] = api.apply_end
    eligibility = seed.eligibility.model_copy(update={
        name: getattr(api.eligibility, name)
        for name in ("age_min", "age_max", "income", "manual_checks")
        if _blank(getattr(seed.eligibility, name)) and not _blank(getattr(api.eligibility, name))})
    if eligibility != seed.eligibility:
        update["eligibility"] = eligibility
    return seed.model_copy(update=update) if update else seed


_VOLATILE = {"as_of", "verified_at"}


def _same_content(a: Policy, b: Policy) -> bool:
    return a.model_dump(exclude=_VOLATILE) == b.model_dump(exclude=_VOLATILE)


def upsert_policies(catalog: CatalogRepo, policies: list[Policy]) -> dict:
    """정책을 넣는다. 같은 정책이 온통청년에도 있으면 youthcenterId로 묶어 보강만 한다.

    돌려주는 값: {"created", "enriched", "updated", "unchanged"}. 내용이 같고 기준일만 다르면 기준일만 갱신한다.
    """
    result = {"created": 0, "enriched": 0, "updated": 0, "unchanged": 0}
    for policy in policies:
        if policy.source == PolicySource.YOUTHCENTER and policy.youthcenter_id:
            seed = _find_seed(catalog, policy)
            if seed is not None:
                merged = _enrich_seed(seed, policy)
                if merged != seed:
                    catalog.put_policy(merged)
                    result["enriched"] += 1
                else:
                    result["unchanged"] += 1
                continue
        existing = catalog.get_policy(policy.policy_id)
        if existing is None:
            catalog.put_policy(policy)
            result["created"] += 1
        elif not _same_content(existing, policy):
            catalog.put_policy(policy)
            result["updated"] += 1
        else:
            if existing != policy:
                catalog.put_policy(policy)
            result["unchanged"] += 1
    return result


# ---------------------------------------------------------------- 기업
def upsert_companies(catalog: CatalogRepo, companies: list[CompanyRecord]) -> dict:
    """강소기업 같은 기업 시드를 넣는다. 돌려주는 값: {"created", "updated", "unchanged"}.

    같은 기업이 이미 있으면 배지를 합친다. 다른 출처(청끌기업 시드 등)에서 붙은 배지를 지우지 않는다.
    내용이 같고 기준일만 다르면 기준일만 갱신하고 unchanged로 센다.
    """
    result = {"created": 0, "updated": 0, "unchanged": 0}
    for company in companies:
        existing = catalog.get_company(company.company_id)
        if existing is None:
            catalog.put_company(company)
            result["created"] += 1
            continue
        incoming = {(b.type, b.label, b.source) for b in company.highlights}
        kept = [b for b in existing.highlights if (b.type, b.label, b.source) not in incoming]
        merged = existing.model_copy(update={
            "name": company.name, "biz_no": company.biz_no or existing.biz_no, "sido": company.sido or existing.sido,
            "industry": company.industry or existing.industry, "size": company.size or existing.size,
            "highlights": kept + list(company.highlights),
            # 기업 항목의 출처는 처음 넣은 쪽을 따른다. 같은 출처가 다시 오면 기준일만 새로 쓴다
            "as_of": company.as_of if existing.source == company.source else existing.as_of,
        })
        if merged.model_dump(exclude={"as_of"}) == existing.model_dump(exclude={"as_of"}):
            result["unchanged"] += 1
        else:
            result["updated"] += 1
        if merged != existing:
            catalog.put_company(merged)
    return result
