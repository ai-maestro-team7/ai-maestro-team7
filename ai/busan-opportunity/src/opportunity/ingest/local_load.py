"""저장해 둔 원본 응답을 정규화해 메모리 저장소에 넣고 건수를 요약한다. 네트워크와 AWS는 부르지 않는다.

    PYTHONPATH=src python -m opportunity.ingest.local_load --raw ~/team07-opp-data/raw --day 2026-11-20 \\
        [--out ~/team07-opp-data]

읽는 파일 (`{raw}/{출처}/{day}/`)
- `youthcenter/`: `policies_p*.json`(손으로 받은 것) 또는 `list-*.json`(수집 실행기가 남긴 것)
- `work24_gangso/`: `region{코드}_p*.xml` 또는 `region{코드}-*.xml`
- `work24_codes/`: `CMCD_1.xml`(지역), `CMCD_2.xml`(직종). 없으면 표 없이 정규화한다.

`--out DIR`을 주면 `DIR/normalized/{day}/policies.jsonl`, `companies.jsonl`(카멜 표기 JSON 한 줄에 하나)을 쓴다.
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
from ..store.memory import MemoryCatalog
from . import codes
from .field_maps import WORK24_GANGSO, YOUTHCENTER
from .http import FetchError, as_list, parse_body, walk
from .normalize import SkipRecord, normalize_gangso, normalize_youthcenter
from .pipeline import upsert_companies, upsert_policies

POLICY_PATTERNS = ("policies_p*.json", "list-*.json")
GANGSO_PATTERNS = ("region*_p*.xml", "region*-*.xml")
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
    _, summary, policies, companies = load(raw, args.day)
    if args.out:
        folder = args.out.expanduser() / "normalized" / args.day
        summary["written"] = {
            "policies": write_jsonl(folder / "policies.jsonl", sorted(policies, key=lambda p: p.policy_id)),
            "companies": write_jsonl(folder / "companies.jsonl", sorted(companies, key=lambda c: c.company_id)),
            "dir": str(folder),
        }
    json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

