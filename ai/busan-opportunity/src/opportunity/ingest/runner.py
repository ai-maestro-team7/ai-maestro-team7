"""수집 배치 실행기. 출처마다 목록 → 정규화 → 상세 → 적재를 돌리고 결과를 `runs/{날짜}.json`에 남긴다.

한 출처가 실패해도 나머지는 계속한다. 인증키와 키가 든 URL은 결과·로그·저장 경로 어디에도 남기지 않는다.
"""

import json
import logging
from collections.abc import Callable, Sequence
from datetime import date, datetime

from ..config import OpportunityConfig
from ..core import clock
from ..models.posting import PostingSnapshot
from ..ports import CatalogRepo, RawStore, Secrets
from . import alio, work24, youthcenter
from .field_maps import DETAIL_MAX_PER_RUN
from .http import FetchError, HttpGet, KeyCache, default_http_get
from .normalize import SkipRecord, normalize_alio, normalize_work24, normalize_youthcenter
from .pipeline import expire_postings, upsert_policies, upsert_postings

log = logging.getLogger(__name__)

JOB_CODES_KEY = "seed/codes/work24_job_codes.json"  # {"직종코드": {"name", "middle", "major"}} (공통코드 시드)
POSTING_SOURCES = {
    "work24": (work24, normalize_work24),
    "alio": (alio, normalize_alio),
}
ALL_SOURCES = ("work24", "alio", "youthcenter")


def _load_job_codes(raw_store: RawStore) -> dict:
    body = raw_store.get(JOB_CODES_KEY)
    if body is None:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        log.warning("직종 코드 시드를 읽지 못함 key=%s", JOB_CODES_KEY)
        return {}
    return data if isinstance(data, dict) else {}


def _wants_detail(config: OpportunityConfig, snap: PostingSnapshot) -> bool:
    """상세는 부산·수도권 근무 공고 가운데 데모 직무군에만 부른다. 직무군을 모르면 빼지 않는다."""
    region = snap.work_region
    if region.unknown or region.sido not in {config.data.busan_sido, *config.data.capital_area_sido}:
        return False
    families = config.data.demo_job_families
    return not (snap.job.major and families and snap.job.major not in families)


def _status(listed: int, normalized: int, failed_pages: int) -> str:
    if listed == 0:
        return "FAILED" if failed_pages else "EMPTY"
    if normalized == 0:
        return "NEEDS_MAPPING"  # 응답은 왔는데 하나도 정규화하지 못했다. 매핑표(field_maps.py)를 확인한다
    return "PARTIAL" if failed_pages else "OK"


def _run_postings(name: str, config, catalog, raw_store, keys, *, when, day, http_get, sleep) -> dict:
    module, normalize = POSTING_SOURCES[name]
    client = module.client(keys, raw_store, day=day, http_get=http_get, sleep=sleep)
    job_codes = _load_job_codes(raw_store) if name == "work24" else {}

    pages = client.fetch_list()
    skipped: dict[str, int] = {}
    snapshots: dict[str, PostingSnapshot] = {}
    records: dict[str, dict] = {}
    for record in pages.records:
        try:
            snap = normalize(record, as_of=when, job_codes=job_codes)
        except SkipRecord as e:
            skipped[e.reason] = skipped.get(e.reason, 0) + 1
            continue
        snapshots[snap.job_posting_id] = snap
        records[snap.job_posting_id] = record

    fetched = failed = 0
    for posting_id, snap in list(snapshots.items()):
        if fetched + failed >= DETAIL_MAX_PER_RUN:
            pages.warnings.append(f"상세 호출 상한 {DETAIL_MAX_PER_RUN}건에서 멈춤")
            break
        if not _wants_detail(config, snap):
            continue
        try:
            detail = client.fetch_detail(posting_id.split("-", 1)[1])
        except FetchError as e:
            failed += 1
            pages.warnings.append(f"상세 실패 {posting_id}: {e}")
            continue
        if detail is None:
            continue
        fetched += 1
        try:
            snapshots[posting_id] = normalize(records[posting_id], as_of=when, detail=detail, job_codes=job_codes)
        except SkipRecord as e:  # 상세 때문에 정규화가 깨지면 목록 값으로 둔다
            pages.warnings.append(f"상세 정규화 건너뜀 {posting_id}: {e.reason}")

    stats = upsert_postings(config, catalog, list(snapshots.values()), as_of=when)
    return {
        "status": _status(len(pages.records), len(snapshots), pages.failed_pages),
        "listed": len(pages.records), "normalized": len(snapshots), "skipped": skipped,
        "pages": pages.pages, "failedPages": pages.failed_pages,
        "detailFetched": fetched, "detailFailed": failed, "warnings": pages.warnings,
        **stats, "_postingIds": list(snapshots),
    }


def _run_policies(catalog, raw_store, keys, *, when, day, http_get, sleep) -> dict:
    pages = youthcenter.client(keys, raw_store, day=day, http_get=http_get, sleep=sleep).fetch_list()
    skipped: dict[str, int] = {}
    policies = {}
    for record in pages.records:
        try:
            policy = normalize_youthcenter(record, as_of=when)
        except SkipRecord as e:
            skipped[e.reason] = skipped.get(e.reason, 0) + 1
            continue
        policies[policy.policy_id] = policy
    stats = upsert_policies(catalog, list(policies.values()))
    return {
        "status": _status(len(pages.records), len(policies), pages.failed_pages),
        "listed": len(pages.records), "normalized": len(policies), "skipped": skipped,
        "pages": pages.pages, "failedPages": pages.failed_pages, "warnings": pages.warnings, **stats,
    }


def run_ingest(config: OpportunityConfig, catalog: CatalogRepo, raw_store: RawStore, secrets: Secrets, *,
               sources: Sequence[str], as_of: str | date | datetime | None = None,
               http_get: HttpGet | None = None, sleep: Callable[[float], None] | None = None) -> dict:
    """출처별로 수집해 적재한다. 출처별 건수와 실패는 `runs/{날짜}.json`에 남긴다.

    - 한 출처가 실패해도 다음 출처로 간다. 실패한 출처는 `status=FAILED`와 오류 종류만 남는다.
    - 하나라도 성공했을 때만 `catalog.set_data_as_of`를 부른다. 전부 실패하면 기준 시각을 올리지 않아 stale로 보인다.
    - 시연 중에는 부르지 않는다. 새벽 배치에서만 쓴다.
    """
    when = clock.parse_as_of(as_of)
    day = clock.day(when)
    fetch = http_get or default_http_get
    keys = KeyCache(secrets)
    report: dict = {"asOf": clock.iso(when), "sources": {}}

    for name in sources:
        try:
            if name in POSTING_SOURCES:
                result = _run_postings(name, config, catalog, raw_store, keys, when=when, day=day,
                                       http_get=fetch, sleep=sleep)
            elif name == "youthcenter":
                result = _run_policies(catalog, raw_store, keys, when=when, day=day, http_get=fetch, sleep=sleep)
            else:
                result = {"status": "FAILED", "error": f"알 수 없는 출처: {name}"}
        except Exception as e:  # 한 출처의 실패가 다른 출처를 막지 않게 한다
            reason = str(e) if isinstance(e, FetchError) else ""
            result = {"status": "FAILED", "error": type(e).__name__ + (f": {reason}" if reason else "")}
            log.error("수집 실패 source=%s error=%s", name, result["error"])
        report["sources"][name] = result

    seen = [i for r in report["sources"].values() for i in r.pop("_postingIds", [])]  # 리포트에는 싣지 않는다
    try:
        report["expired"] = expire_postings(config, catalog, as_of=when, job_posting_ids=seen)
    except Exception as e:
        report["expired"] = 0
        report["expireError"] = type(e).__name__
        log.error("마감 처리 실패 error=%s", type(e).__name__)

    succeeded = any(r["status"] in ("OK", "PARTIAL", "EMPTY") for r in report["sources"].values())
    report["ok"] = succeeded and all(r["status"] != "FAILED" for r in report["sources"].values())
    raw_store.put(f"runs/{day}.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    if succeeded:
        catalog.set_data_as_of(clock.iso(when))
    return report
