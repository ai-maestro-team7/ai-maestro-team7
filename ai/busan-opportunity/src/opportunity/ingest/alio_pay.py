"""알리오 경영공시 「직원 평균보수」 수집 (B-01). 기관마다 일반정규직 1인당 평균 보수액을 연도별로 읽는다.

공개 누리집이라 인증키가 없다. 목록 한 번(POST)과 기관마다 보고서 한 번(GET)을 부른다. 보고서 HTML에는 공시
담당자 이름·전화번호가 있어서 저장하지 않고, 필요한 숫자만 읽어 `OrgPay`로 넘긴다.
"""

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlencode

from ..core import clock
from ..models.posting import OrgPay, OrgPayYear
from .field_maps import ALIO_PAY, ALIO_PAY_SOURCE
from .http import FetchError, HttpGet, HttpPostJson

_YEAR = re.compile(r"(\d{4})\s*년\s*(결산|예산)?")
_AS_OF = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_NUMBER = re.compile(r"^-?[\d,]+(\.\d+)?$")


class _Rows(HTMLParser):
    """표의 행을 칸 글자 목록으로 모은다. 표가 여러 개여도 문서 순서대로 한 줄씩 쌓는다."""

    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._row is not None and self._cell is not None:
            self._row.append(re.sub(r"\s+", " ", unescape("".join(self._cell))).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _number(text: str) -> float | None:
    t = (text or "").replace(" ", "")
    return float(t.replace(",", "")) if _NUMBER.match(t) else None


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


@dataclass
class ParsedPay:
    years: list[OrgPayYear] = field(default_factory=list)
    tenure_by_year: dict[int, int] = field(default_factory=dict)
    as_of: str | None = None


def parse_report(html: str) -> ParsedPay | None:
    """보고서 HTML에서 일반정규직 표의 연도별 1인당 평균 보수액(천 원 → 만 원)과 평균근속연수를 읽는다.

    무기계약직·단시간 표는 읽지 않는다. 일반정규직 표가 없거나 금액이 하나도 없으면 None.
    """
    parser = _Rows()
    parser.feed(html or "")
    result = ParsedPay()
    columns: list[tuple[int, bool] | None] = []
    in_section = seen_section = False
    tenure_done = False
    for row in parser.rows:
        first = _compact(row[0])
        if first.startswith("기준일"):
            for cell in row[1:]:
                m = _AS_OF.search(cell)
                if m:
                    result.as_of = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                    break
        if first.startswith("정규직("):
            in_section = "일반정규직" in first
            seen_section = seen_section or in_section
            columns = []
            continue
        if not in_section:
            continue
        if first == "구분":
            columns = []
            for cell in row[1:]:
                m = _YEAR.search(cell)
                columns.append((int(m.group(1)), m.group(2) == "예산") if m else None)
        elif first.startswith("1인당평균보수") and columns and not result.years:
            for col, cell in zip(columns, row[1:]):
                value = _number(cell)
                if col and value is not None and value > 0:
                    result.years.append(OrgPayYear(year=col[0], average=round(value / 10), budget=col[1]))
        elif first.startswith("평균근속연수") and columns and not tenure_done:
            tenure_done = True
            for col, cell in zip(columns, row[1:]):
                value = _number(cell)
                if col and value is not None and value > 0:
                    result.tenure_by_year[col[0]] = round(value)
    if not seen_section or not result.years:
        return None
    result.years.sort(key=lambda y: (y.year, y.budget))
    return result


def to_org_pay(org: dict, parsed: ParsedPay, *, checked_day: str) -> OrgPay | None:
    """목록의 기관 한 줄과 읽은 표로 `OrgPay`를 만든다. 결산 연도가 하나도 없으면 None."""
    settled = [y for y in parsed.years if not y.budget]
    if not settled:
        return None
    latest = settled[-1]
    page = ALIO_PAY["page_url"] + "?" + urlencode({"apbaId": org["apbaId"], "reportFormRootNo": ALIO_PAY["form"],
                                                    "disclosureNo": org.get("disclosureNo") or ""})
    return OrgPay(org_id=org["apbaId"], name=org["apbaNa"].strip(), org_type=org.get("typeNa"),
                  ministry=org.get("jidtNa"), years=parsed.years, latest_year=latest.year,
                  latest_average=latest.average, tenure_months=parsed.tenure_by_year.get(latest.year),
                  source=ALIO_PAY_SOURCE, as_of=parsed.as_of or checked_day, source_url=page)


def fetch_org_pays(http_get: HttpGet, http_post: HttpPostJson, *, timeout: float,
                   sleep: Callable[[float], None] = time.sleep,
                   now: Callable[[], object] = clock.now_kst) -> tuple[list[OrgPay], dict]:
    """목록을 받고 기관마다 보고서를 읽는다. 한 기관이 실패해도 다음 기관으로 간다. 돌려주는 값: (기관 목록, 건수 요약)."""
    body = {"apbaType": [], "jidtDptm": [], "area": [], "apbaId": "", "reportFormRootNo": ALIO_PAY["form"],
            "quart": ""}
    listing = json.loads(http_post(ALIO_PAY["list_url"], body, timeout).decode("utf-8"))
    orgs = ((listing or {}).get("data") or {}).get("organList") or []
    day = clock.day(now())
    pays: list[OrgPay] = []
    stats = {"listed": len(orgs), "noReport": 0, "failed": 0, "unparsed": 0, "warnings": []}
    for i, org in enumerate(orgs):
        if not org.get("disclosureNo") or not org.get("apbaId"):
            stats["noReport"] += 1
            continue
        if i:
            sleep(ALIO_PAY["delay_seconds"])
        url = ALIO_PAY["report_url"] + "?" + urlencode({"disclosureNo": org["disclosureNo"]})
        html = None
        for attempt in range(2):  # 타임아웃 5초에 한 번 다시 시도한다 (AGENTS.md)
            try:
                html = http_get(url, timeout).decode("utf-8", errors="replace")
                break
            except FetchError as e:
                if attempt:
                    stats["failed"] += 1
                    stats["warnings"].append(f"보고서 실패 {org['apbaId']}: {e}")
                else:
                    sleep(ALIO_PAY["delay_seconds"])
        if html is None:
            continue
        parsed = parse_report(html)
        pay = to_org_pay(org, parsed, checked_day=day) if parsed else None
        if pay is None:
            stats["unparsed"] += 1
            continue
        pays.append(pay)
    return pays, stats
