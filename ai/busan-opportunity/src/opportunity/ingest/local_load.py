"""저장해 둔 원본 응답을 정규화해 메모리 저장소에 넣고 건수를 요약한다. 네트워크와 AWS는 부르지 않는다.

    PYTHONPATH=src python -m opportunity.ingest.local_load --raw ~/team07-opp-data/raw --day 2026-11-20 \\
        [--out ~/team07-opp-data]

읽는 파일 (`{raw}/{출처}/{day}/`)
- `youthcenter/`: `policies_p*.json`(손으로 받은 것) 또는 `list-*.json`(수집 실행기가 남긴 것)
- `work24_gangso/`: `region{코드}_p*.xml` 또는 `region{코드}-*.xml`
- `work24_codes/`: `CMCD_1.xml`(지역), `CMCD_2.xml`(직종). 없으면 표 없이 정규화한다.
- `alio/`: `list_p*.json`(손으로 받은 것) 또는 `list-*.json`(수집 실행기가 남긴 것). 상세(`detail_*.json`)는 읽지 않는다.

`--out DIR`을 주면 `DIR/normalized/{day}/policies.jsonl`, `companies.jsonl`, `postings.jsonl`
(카멜 표기 JSON 한 줄에 하나. 공고는 최신 스냅샷)을 쓴다.
요약에는 건수와 이유만 남긴다. 원문, 담당자 이름, 인증키는 출력하지 않는다.
"""

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from ..config import OpportunityConfig, load_config
from ..core import clock
from ..models.enums import PeriodType
from ..models.policy import ALWAYS_APPLY_END, Policy
from ..models.posting import PostingSnapshot
from ..store.memory import MemoryCatalog
from . import codes
from .field_maps import ALIO, WORK24_GANGSO, YOUTHCENTER
from .http import FetchError, as_list, parse_body, walk
from .normalize import SkipRecord, normalize_alio, normalize_gangso, normalize_youthcenter, parse_alio_region
from .pipeline import upsert_companies, upsert_policies, upsert_postings

POLICY_PATTERNS = ("policies_p*.json", "list-*.json")
GANGSO_PATTERNS = ("region*_p*.xml", "region*-*.xml")
POSTING_PATTERNS = ("list_p*.json", "list-*.json")
REGION_CODES_FILE = "CMCD_1.xml"
JOB_CODES_FILE = "CMCD_2.xml"
SEOUL_SIDO = "11"  # 요약에서 서울 건수를 셀 때만 쓴다


def _files(folder: Path, patterns: Iterable[str]) -> list[Path]:
    found: dict[str, Path] = {}
    for pattern in patterns:
        for path in folder.glob(pattern):
            found[path.name] = path
    return [found[name] for name in sorted(found)]


def _read_items(paths: list[Path], spec: dict, failures: Counter) -> tuple[list[dict], dict[str, int]]:
    """파일마다 항목을 꺼낸다. 해석하지 못한 파일은 failures에 `unreadable_file`로 센다.

    돌려주는 값: (항목 목록, {파일 묶음 이름: 응답의 전체 건수}). 묶음 이름은 파일 이름의 `_p`·`-` 앞부분이다.
    """
    items: list[dict] = []
    totals: dict[str, int] = {}
    for path in paths:
        try:
            parsed = parse_body(path.read_bytes())
        except (OSError, FetchError):
            failures["unreadable_file"] += 1
            continue
        rows = [r for r in as_list(walk(parsed, spec["list"]["items_path"])) if isinstance(r, dict)]
        items.extend(rows)
        group = path.stem.split("_p")[0].split("-")[0]
        total = walk(parsed, spec["list"]["total_path"])
        try:
            totals[group] = int(str(total).replace(",", ""))
        except (TypeError, ValueError):
            pass
    return items, totals


def _load_region_names(folder: Path) -> dict[str, str]:
    path = folder / REGION_CODES_FILE
    if not path.exists():
        return {}
    try:
        return codes.region_names(path.read_bytes())
    except (OSError, FetchError):
        return {}


def _load_job_codes(folder: Path) -> dict:
    path = folder / JOB_CODES_FILE
    if not path.exists():
        return {}
    try:
        return codes.job_codes(path.read_bytes())
    except (OSError, FetchError):
        return {}


def is_open(policy: Policy, today: str) -> bool:
    """지금 신청할 수 있는 정책. 상시·매월이거나, 정해진 기간 안이다 (`core/policies._timing`의 OPEN과 같은 규칙)."""
    period = policy.application.period_type
    if period in (PeriodType.ALWAYS, PeriodType.MONTHLY):
        return True
    if period != PeriodType.FIXED:
        return False
    if policy.apply_start and today < policy.apply_start:
        return False
    return policy.apply_end == ALWAYS_APPLY_END or today <= policy.apply_end


def stored_postings(catalog: MemoryCatalog) -> list[PostingSnapshot]:
    """공고마다 LATEST가 가리키는 스냅샷. ID 순서다."""
    rows = (catalog.get_snapshot(i, latest.snapshot_id) for i, latest in sorted(catalog.latest.items()))
    return [row for row in rows if row is not None]


def _load_postings(folder: Path, config: OpportunityConfig, catalog: MemoryCatalog, as_of) -> dict:
    """잡알리오 목록 파일을 정규화해 넣고 건수를 센다. 부산·수도권 건수는 근무지 이름 목록 전체로도 센다."""
    busan = config.data.busan_sido
    capital = set(config.data.capital_area_sido)
    failures: Counter = Counter()
    records, totals = _read_items(_files(folder, POSTING_PATTERNS), ALIO, failures)
    snapshots: dict[str, PostingSnapshot] = {}
    listed_sidos: dict[str, set[str]] = {}
    listed_count: dict[str, int] = {}
    duplicates = 0
    region_field = ALIO["fields"]["region_names"]
    for record in records:
        try:
            snap = normalize_alio(record, as_of=as_of, first_sido=busan)
        except SkipRecord as e:
            failures[e.reason] += 1
            continue
        except ValueError:
            failures["invalid_model"] += 1
            continue
        if snap.job_posting_id in snapshots:
            duplicates += 1
        snapshots[snap.job_posting_id] = snap
        names = [n.strip() for n in str(record.get(region_field) or "").split(",") if n.strip()]
        listed_count[snap.job_posting_id] = len(set(names))
        listed_sidos[snap.job_posting_id] = {
            r.sido for r in (parse_alio_region(n) for n in names) if r.sido and not r.unknown}
    stats = upsert_postings(config, catalog, list(snapshots.values()), as_of=as_of)
    stats["needsEnrich"] = len(stats["needsEnrich"])

    stored = [s for s in stored_postings(catalog) if s.job_posting_id in snapshots]
    latest = [catalog.get_latest(s.job_posting_id) for s in stored]
    sidos = [listed_sidos.get(s.job_posting_id, set()) for s in stored]
    counts = [listed_count.get(s.job_posting_id, 0) for s in stored]

    def dist(values) -> dict:
        return dict(sorted(Counter(values).items()))

    return {
        "listed": len(records),
        "apiTotal": sum(totals.values()) if len(totals) == 1 else totals,
        "normalized": len(snapshots),
        "duplicates": duplicates,
        "stored": len(stored),
        "region": {
            "busanAny": sum(busan in found for found in sidos),          # 근무지 목록에 부산이 있다
            "busanOnly": sum(found == {busan} and n == 1 for found, n in zip(sidos, counts)),  # 부산 한 곳
            "busanMulti": sum(busan in found and n > 1 for found, n in zip(sidos, counts)),
            "isBusan": sum(row.is_busan for row in latest),             # LATEST 기준 (여러 곳이면 부산 우선)
            "isCapitalArea": sum(row.is_capital_area for row in latest),
            "capitalAny": sum(bool(found & capital) for found in sidos),
            "capitalOnly": sum(bool(found) and found <= capital for found in sidos),
            "multiRegion": sum(n > 1 for n in counts),
            "unknown": sum(s.work_region.unknown for s in stored),
            "bySido": dist(s.work_region.sido or "unknown" for s in stored),
        },
        "employmentType": dist(s.employment_type.value for s in stored),
        "educationMin": dist(s.education_min.value if s.education_min else "UNKNOWN" for s in stored),
        "careerType": dist(s.career_type.value for s in stored),
        "rolling": sum(s.rolling for s in stored),
        "expired": sum(row.is_expired for row in latest),
        "withOfficialUrl": sum(s.official_url is not None for s in stored),
        "failed": sum(failures.values()),
        "failedBy": dict(sorted(failures.items())),
        "upsert": stats,
    }


def load(raw: Path, day: str, *, config: OpportunityConfig | None = None,
         catalog: MemoryCatalog | None = None) -> tuple[MemoryCatalog, dict, list[Policy], list]:
    """원본을 읽어 정규화하고 메모리 저장소에 넣는다. (저장소, 요약, 정책 목록, 기업 목록)을 돌려준다."""
    config = config or load_config()
    catalog = catalog or MemoryCatalog()
    as_of = clock.parse_as_of(day)
    today = clock.day(as_of)
    busan = config.data.busan_sido
    capital = list(config.data.capital_area_sido)

    region_names = _load_region_names(raw / "work24_codes" / day)
    job_codes = _load_job_codes(raw / "work24_codes" / day)

    # 정책
    policy_failures: Counter = Counter()
    records, policy_totals = _read_items(_files(raw / "youthcenter" / day, POLICY_PATTERNS), YOUTHCENTER,
                                         policy_failures)
    policies: dict[str, Policy] = {}
    duplicates = 0
    for record in records:
        try:
            policy = normalize_youthcenter(record, as_of=as_of, region_names=region_names or None,
                                           first_sido=busan)
        except SkipRecord as e:
            policy_failures[e.reason] += 1
            continue
        except ValueError:  # 모델 검사 실패 (pydantic ValidationError는 ValueError다)
            policy_failures["invalid_model"] += 1
            continue
        if policy.policy_id in policies:
            duplicates += 1
        policies[policy.policy_id] = policy
    policy_stats = upsert_policies(catalog, list(policies.values()))

    # 기업
    company_failures: Counter = Counter()
    rows, company_totals = _read_items(_files(raw / "work24_gangso" / day, GANGSO_PATTERNS), WORK24_GANGSO,
                                       company_failures)
    companies = {}
    for row in rows:
        try:
            company = normalize_gangso(row, as_of=as_of)
        except SkipRecord as e:
            company_failures[e.reason] += 1
            continue
        except ValueError:
            company_failures["invalid_model"] += 1
            continue
        companies[company.company_id] = company
    company_stats = upsert_companies(catalog, list(companies.values()))

    # 공고 (잡알리오)
    posting_summary = _load_postings(raw / "alio" / day, config, catalog, as_of)

    stored = list(catalog.policies.values())
    key_counts = Counter(p.region_key() for p in stored)
    touches = Counter(s for p in stored for s in {r.sido for r in p.regions if r.sido})
    scope_counts = Counter(p.regions[0].scope.value for p in stored if p.regions)
    summary = {
        "day": day,
        "codes": {"regions": len(region_names), "jobs": len(job_codes)},
        "policies": {
            "listed": len(records),
            "apiTotal": sum(policy_totals.values()) if len(policy_totals) == 1 else policy_totals,
            "normalized": len(policies),
            "duplicates": duplicates,
            "stored": len(stored),
            "byRegionKey": {"busan": key_counts.get(busan, 0), "seoul": key_counts.get(SEOUL_SIDO, 0),
                            "national": key_counts.get("00", 0)},
            "includesBusan": touches.get(busan, 0),
            "multiSidoIncludingBusan": sum(
                1 for p in stored if len(p.regions) > 1 and any(r.sido == busan for r in p.regions)),
            "firstScope": dict(sorted(scope_counts.items())),
            "periodType": dict(sorted(Counter(p.application.period_type.value for p in stored).items())),
            "open": sum(is_open(p, today) for p in stored),
            "openBusanOrNational": sum(is_open(p, today) for p in stored if p.region_key() in (busan, "00")),
            "failed": sum(policy_failures.values()),
            "failedBy": dict(sorted(policy_failures.items())),
            "upsert": policy_stats,
        },
        "companies": {
            "listed": len(rows),
            "apiTotal": dict(sorted(company_totals.items())),
            "normalized": len(companies),
            "stored": len(catalog.companies),
            "bySido": {s: len(catalog.list_companies(s)) for s in [busan, *capital]},
            "failed": sum(company_failures.values()),
            "failedBy": dict(sorted(company_failures.items())),
            "upsert": company_stats,
        },
        "postings": posting_summary,
    }
    return catalog, summary, stored, list(catalog.companies.values())


def write_jsonl(path: Path, rows: Iterable) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row.to_api(), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="저장한 공공 API 원본을 정규화해 메모리 저장소에 넣고 건수를 요약한다")
    parser.add_argument("--raw", required=True, type=Path, help="raw 폴더 (예: ~/team07-opp-data/raw)")
    parser.add_argument("--day", required=True, help="수집일 YYYY-MM-DD")
    parser.add_argument("--out", type=Path, help="정규화 결과를 쓸 폴더. normalized/{day}/ 아래에 쓴다")
    args = parser.parse_args(argv)

    raw = args.raw.expanduser()
    catalog, summary, policies, companies = load(raw, args.day)
    if args.out:
        folder = args.out.expanduser() / "normalized" / args.day
        summary["written"] = {
            "policies": write_jsonl(folder / "policies.jsonl", sorted(policies, key=lambda p: p.policy_id)),
            "companies": write_jsonl(folder / "companies.jsonl", sorted(companies, key=lambda c: c.company_id)),
            "postings": write_jsonl(folder / "postings.jsonl", stored_postings(catalog)),
            "dir": str(folder),
        }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

