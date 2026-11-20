"""부산 근무지 주변 생활 정보 (축제·대중교통·통근) 원본을 `LocalLifeData`로 만든다. 네트워크와 AWS는 부르지 않는다.

    PYTHONPATH=src python -m opportunity.ingest.local_data --raw ~/team07-opp-data/raw --day 2026-11-20 \\
        --out ~/team07-opp-data [--commute commute.csv --commute-source 출처 --commute-as-of YYYY-MM-DD]

읽는 파일
- `{raw}/busan_festival/{day}/festival_p*.json`: 부산광역시 부산축제정보 (`getFestivalKr.item[]`). 기준일은 수집일(day).
- `{raw}/files/{day}/busan_subway_lines_*.csv`: 부산교통공사 도시철도 노선정보. 기준일은 `데이터기준일자` 열.
- `{raw}/files/{day}/bus_stops_by_sido_YYYYMMDD.csv`: 시·도별 버스정류장 수. 기준일은 파일 이름의 날짜.
- `{raw}/files/{day}/busan_bus_route_usage_YYYYMMDD.csv`: 시내·마을버스 노선별 교통카드 이용 건수. 기준일은 파일 이름의 날짜.

`--out DIR`이면 `DIR/seed/local_life.json`(LocalLifeData.to_api())을 쓴다.
숫자는 파일에서 센 값만 쓴다. 통근 표는 길찾기 API가 정해질 때까지 비워 두고, `--commute`로 준 CSV만 넣는다.
축제 연락처(CNTCT_TEL)는 넣지 않는다. 요약에는 건수만 남긴다.
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from ..models.region import FestivalInfo, LocalLifeData, TransitInfo

FESTIVAL_SOURCE = "부산광역시 부산축제정보"
SUBWAY_SOURCE = "부산교통공사 도시철도노선정보"
BUS_STOP_SOURCE = "한국교통안전공단 전국 대중교통 버스정류장 현황"
BUS_ROUTE_SOURCE = "부산광역시 시내버스 및 마을버스 노선별 이용 건수"

FESTIVAL_DIR = "busan_festival"
FESTIVAL_PATTERN = "festival_p*.json"
FILES_DIR = "files"
SUBWAY_PATTERN = "busan_subway_lines_*.csv"
BUS_STOP_PATTERN = "bus_stops_by_sido_*.csv"
BUS_ROUTE_PATTERN = "busan_bus_route_usage_*.csv"
BUSAN_SIDO_NAME = "부산"  # 버스정류장 표의 `구분` 값

# 대중교통 한 줄 문구. 숫자만 파일에서 채운다
SUBWAY_LABEL = "부산 도시철도"
SUBWAY_VALUE = "{lines}개 노선 · {stations}"
SUBWAY_STATION = "{line} {count}개 역"
BUS_ROUTE_LABEL = "부산 시내·마을버스"
BUS_ROUTE_VALUE = "{routes:,}개 노선 · 교통카드 이용 연 {rides:,}건"
BUS_STOP_LABEL = "부산 버스정류장"
BUS_STOP_VALUE = "{total:,}곳 (지붕 있는 정류장 {covered:,}곳)"

# 축제 이름 끝의 언어 표기: "(한,영, 중간,중번,일)", "(한)//영,중간,중번,일", "(한, 영)", "(한)"
_LANG_SUFFIX = re.compile(r"\s*\((?:\s*(?:한|영|중간|중번|일)\s*,?)+\)\s*(?://[\s한영중간번일,]*)?$")
_LINE_NO = re.compile(r"(\d+)\s*호선")
_FILE_DAY = re.compile(r"_(\d{4})(\d{2})(\d{2})\.csv$")
_SIGUNGU = re.compile(r"^\d{5}$")


class LocalDataError(ValueError):
    """원본이나 시드가 규칙에 어긋난다. 출처·기준일이 없는 항목은 받지 않는다."""


# ---------------------------------------------------------------- 공통
def _text(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _int(value) -> int:
    return int(str(value).replace(",", "").strip())


def _read_csv(data: bytes) -> list[dict[str, str]]:
    """UTF-8(BOM 포함)으로 읽고, 안 되면 CP949로 읽는다."""
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
                for row in csv.DictReader(io.StringIO(text))]
    raise LocalDataError("CSV 인코딩을 읽지 못했다")


def _file_day(path: Path) -> str:
    found = _FILE_DAY.search(path.name)
    if not found:
        raise LocalDataError(f"파일 이름에 기준일(YYYYMMDD)이 없다: {path.name}")
    return "-".join(found.groups())


def _one(folder: Path, pattern: str) -> Path | None:
    """같은 종류가 여러 개면 이름이 가장 뒤인 것(가장 최근 기준일)."""
    paths = sorted(folder.glob(pattern))
    return paths[-1] if paths else None


# ---------------------------------------------------------------- 축제
def festival_title(raw: str) -> str:
    """"부산바다축제(한,영, 중간,중번,일)" → "부산바다축제". 언어 표기가 아닌 괄호("(BOF)")는 둔다."""
    return _LANG_SUFFIX.sub("", raw.strip()).strip()


def _url(value) -> str | None:
    text = _text(value)
    return text if text and text.lower().startswith(("http://", "https://")) else None


def parse_festivals(body: bytes | str | dict, *, as_of: str) -> list[FestivalInfo]:
    """축제정보 응답 한 쪽 → FestivalInfo 목록. 이름이 없는 항목은 버린다. 연락처는 넣지 않는다."""
    data = json.loads(body) if isinstance(body, (bytes, str)) else body
    items = (data.get("getFestivalKr") or {}).get("item") or []
    if isinstance(items, dict):
        items = [items]
    out = []
    for item in items:
        seq, title = _text(item.get("UC_SEQ")), _text(item.get("MAIN_TITLE"))
        if seq is None or title is None:
            continue
        out.append(FestivalInfo(
            festival_id=f"fest-{seq}", title=festival_title(title), gugun=_text(item.get("GUGUN_NM")),
            place=_text(item.get("MAIN_PLACE")), period=_text(item.get("USAGE_DAY_WEEK_AND_TIME")),
            traffic=_text(item.get("TRFC_INFO")), url=_url(item.get("HOMEPAGE_URL")),
            source=FESTIVAL_SOURCE, as_of=as_of,
        ))
    return out


# ---------------------------------------------------------------- 대중교통
def _line_name(raw: str) -> str:
    found = _LINE_NO.search(raw)
    return f"{found.group(1)}호선" if found else raw


def parse_subway_lines(data: bytes) -> TransitInfo | None:
    """노선 수와 노선별 역 수(`정거장구성`의 항목 수). 기준일은 `데이터기준일자` 열."""
    rows = [r for r in _read_csv(data) if r.get("노선명")]
    if not rows:
        return None
    days = {r.get("데이터기준일자") for r in rows if r.get("데이터기준일자")}
    if len(days) != 1:
        raise LocalDataError("도시철도 노선정보의 데이터기준일자가 하나가 아니다")
    stations = [SUBWAY_STATION.format(line=_line_name(r["노선명"]),
                                      count=len([s for s in r.get("정거장구성", "").split(",") if s.strip()]))
                for r in rows]
    return TransitInfo(label=SUBWAY_LABEL, value=SUBWAY_VALUE.format(lines=len(rows), stations=" · ".join(stations)),
                       source=SUBWAY_SOURCE, as_of=days.pop())


def parse_bus_stops(data: bytes, *, as_of: str) -> TransitInfo | None:
    """시·도별 버스정류장 표에서 부산 행만."""
    for row in _read_csv(data):
        if row.get("구분") == BUSAN_SIDO_NAME:
            return TransitInfo(label=BUS_STOP_LABEL,
                               value=BUS_STOP_VALUE.format(total=_int(row["전체버스정류장"]),
                                                           covered=_int(row["유개버스정류장"])),
                               source=BUS_STOP_SOURCE, as_of=as_of)
    return None


def parse_bus_routes(data: bytes, *, as_of: str) -> TransitInfo | None:
    """노선 수(심야·아침 등 운행 구분도 한 노선으로 센다)와 교통카드 이용 건수 합계."""
    rows = [r for r in _read_csv(data) if r.get("노선")]
    if not rows:
        return None
    rides = sum(_int(r["교통카드건수합계"]) for r in rows)
    return TransitInfo(label=BUS_ROUTE_LABEL, value=BUS_ROUTE_VALUE.format(routes=len(rows), rides=rides),
                       source=BUS_ROUTE_SOURCE, as_of=as_of)


# ---------------------------------------------------------------- 통근
def load_commute_csv(path: str | Path) -> dict[str, int]:
    """열 from_sigungu, to_sigungu, minutes → {"거주 시군구>근무 시군구": 대중교통 분}. 형식이 틀린 행은 거부한다."""
    table: dict[str, int] = {}
    for n, row in enumerate(_read_csv(Path(path).expanduser().read_bytes()), start=2):
        src, dst, minutes = row.get("from_sigungu", ""), row.get("to_sigungu", ""), row.get("minutes", "")
        if not (_SIGUNGU.match(src) and _SIGUNGU.match(dst)):
            raise LocalDataError(f"통근 CSV {n}행: 시군구 코드는 5자리여야 한다")
        try:
            value = _int(minutes)
        except ValueError:
            raise LocalDataError(f"통근 CSV {n}행: minutes가 정수가 아니다") from None
        if value <= 0:
            raise LocalDataError(f"통근 CSV {n}행: minutes는 0보다 커야 한다")
        table[f"{src}>{dst}"] = value
    return table


# ---------------------------------------------------------------- 묶기·검사
def validate(data: LocalLifeData) -> LocalLifeData:
    """출처·기준일이 빈 항목이 있으면 거부한다. 통근 표가 있으면 통근 출처·기준일도 있어야 한다."""
    for f in data.festivals:
        if not (f.source.strip() and f.as_of.strip()):
            raise LocalDataError(f"축제 {f.festival_id}에 출처나 기준일이 없다")
    for t in data.transit:
        if not (t.source.strip() and t.as_of.strip()):
            raise LocalDataError(f"대중교통 '{t.label}'에 출처나 기준일이 없다")
    if data.commute_minutes and not ((data.commute_source or "").strip() and (data.commute_as_of or "").strip()):
        raise LocalDataError("통근 표에 출처나 기준일이 없다")
    return data


def load_local_life(path_or_bytes: str | Path | bytes | dict) -> LocalLifeData:
    """`seed/local_life.json`(경로, 바이트, dict) → LocalLifeData. 입구가 S3에서 읽어 `Deps.local_life`에 넣는다."""
    if isinstance(path_or_bytes, dict):
        raw = path_or_bytes
    else:
        body = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).expanduser().read_bytes()
        raw = json.loads(body)
    try:
        data = LocalLifeData.model_validate(raw)
    except ValidationError as e:
        raise LocalDataError(f"local_life 시드가 모델에 맞지 않는다: {e.error_count()}개 오류") from e
    return validate(data)


def build_local_life_data(raw: Path, day: str, *, commute: dict[str, int] | None = None,
                          commute_source: str | None = None, commute_as_of: str | None = None) -> LocalLifeData:
    """원본 폴더 → LocalLifeData. 없는 파일은 건너뛴다. 축제는 UC_SEQ로 중복을 뺀다."""
    festivals: dict[str, FestivalInfo] = {}
    for path in sorted((raw / FESTIVAL_DIR / day).glob(FESTIVAL_PATTERN)):
        for f in parse_festivals(path.read_bytes(), as_of=day):
            festivals.setdefault(f.festival_id, f)

    files = raw / FILES_DIR / day
    transit: list[TransitInfo | None] = []
    if path := _one(files, SUBWAY_PATTERN):
        transit.append(parse_subway_lines(path.read_bytes()))
    if path := _one(files, BUS_ROUTE_PATTERN):
        transit.append(parse_bus_routes(path.read_bytes(), as_of=_file_day(path)))
    if path := _one(files, BUS_STOP_PATTERN):
        transit.append(parse_bus_stops(path.read_bytes(), as_of=_file_day(path)))

    return validate(LocalLifeData(
        festivals=list(festivals.values()), transit=[t for t in transit if t is not None],
        commute_minutes=commute or {}, commute_source=commute_source if commute else None,
        commute_as_of=commute_as_of if commute else None,
    ))


def summarize(data: LocalLifeData) -> dict:
    return {
        "festivals": len(data.festivals),
        "festivalsByGugun": dict(Counter(f.gugun or "-" for f in data.festivals).most_common()),
        "transit": [f"{t.label}: {t.value} ({t.as_of})" for t in data.transit],
        "commutePairs": len(data.commute_minutes),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="부산 주변 생활 정보 원본을 seed/local_life.json으로 만든다")
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--day", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--commute", type=Path, help="from_sigungu,to_sigungu,minutes CSV")
    parser.add_argument("--commute-source")
    parser.add_argument("--commute-as-of")
    args = parser.parse_args(argv)

    commute = load_commute_csv(args.commute) if args.commute else None
    if commute and not (args.commute_source and args.commute_as_of):
        parser.error("--commute에는 --commute-source와 --commute-as-of가 필요하다")
    try:
        data = build_local_life_data(args.raw.expanduser(), args.day, commute=commute,
                                     commute_source=args.commute_source, commute_as_of=args.commute_as_of)
    except LocalDataError as e:
        print(f"실패: {e}", file=sys.stderr)
        return 1
    if args.out:
        target = args.out.expanduser() / "seed" / "local_life.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data.to_api(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"썼다: {target}")
    print(json.dumps(summarize(data), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
