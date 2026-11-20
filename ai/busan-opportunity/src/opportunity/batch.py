"""수집 배치의 입구 (B-01 수집, B-02 보강). 백엔드 Lambda가 일정 이벤트를 받아 `run_batch`를 부른다.

한 번 부를 때마다 한 걸음만 하고, 남은 일이 있으면 `next`로 다음 이벤트를 돌려준다. 부르는 쪽(백엔드)이
`next`를 다시 비동기로 호출하면 Lambda 실행 시간 안에서 이어 달린다 (면접 처리와 같은 방식).

  {"step": "ingest"}                         매일 수집 (config.batch.daily_sources)
  {"step": "ingest", "sources": ["work24_gangso"]}   출처를 골라 수집 (주 1회 강소기업 등)
  {"step": "enrich", "ids": [...]}           바뀐 공고 보강 (임베딩, 배지, 지역인재, 부산 대안 후보)

시연 중에는 부르지 않는다. 공공 API는 이 배치에서만 부른다.
"""

import logging
from collections.abc import Callable
from datetime import date, datetime

from .deps import Deps
from .enrich.pipeline import enrich_postings
from .ingest.runner import ALL_SOURCES, run_ingest
from .models.errors import invalid_input
from .ports import RawStore, Secrets

log = logging.getLogger(__name__)
STEP_INGEST = "ingest"
STEP_ENRICH = "enrich"


def run_batch(event: dict, deps: Deps, raw_store: RawStore, secrets: Secrets, *,
              as_of: str | date | datetime | None = None, http_get: Callable | None = None) -> dict:
    """한 걸음을 실행한다. 돌려주는 값: {"step", "result", "next"}. next가 None이면 끝났다."""
    step = (event or {}).get("step")
    if step == STEP_INGEST:
        return _ingest(event, deps, raw_store, secrets, as_of=as_of, http_get=http_get)
    if step == STEP_ENRICH:
        return _enrich(event, deps, as_of=as_of)
    raise invalid_input("배치 step은 ingest 또는 enrich여야 한다")


def _ingest(event, deps, raw_store, secrets, *, as_of, http_get) -> dict:
    """출처를 하나씩 수집한다. 한 출처가 실패해도 다음 출처로 간다 (실패는 result에 남는다)."""
    pending = list(event.get("sources") or deps.config.batch.daily_sources)
    unknown = [name for name in pending if name not in ALL_SOURCES]
    if unknown:
        raise invalid_input("알 수 없는 출처가 있다", sources=unknown)
    ids = list(event.get("ids") or [])
    if not pending:
        return {"step": STEP_INGEST, "result": {}, "next": _enrich_event(ids)}
    source, rest = pending[0], pending[1:]
    report = run_ingest(deps.config, deps.catalog, raw_store, secrets, sources=[source], as_of=as_of,
                        **({"http_get": http_get} if http_get else {}))
    result = report["sources"].get(source, {})
    ids += [i for i in result.pop("needsEnrich", []) if i not in ids]
    log.info("수집 source=%s status=%s", source, result.get("status"))
    nxt = {"step": STEP_INGEST, "sources": rest, "ids": ids} if rest else _enrich_event(ids)
    return {"step": STEP_INGEST, "source": source, "result": result, "next": nxt}


def _enrich(event, deps, *, as_of) -> dict:
    """바뀐 공고를 enrichChunk개씩 보강한다."""
    ids = list(event.get("ids") or [])
    chunk = deps.config.batch.enrich_chunk
    now, rest = ids[:chunk], ids[chunk:]
    result = enrich_postings(deps, now, as_of=as_of) if now else {"enriched": 0, "failed": 0, "alts": 0}
    log.info("보강 enriched=%s failed=%s 남음=%s", result.get("enriched"), result.get("failed"), len(rest))
    return {"step": STEP_ENRICH, "result": result, "next": _enrich_event(rest)}


def _enrich_event(ids: list[str]) -> dict | None:
    return {"step": STEP_ENRICH, "ids": ids} if ids else None
