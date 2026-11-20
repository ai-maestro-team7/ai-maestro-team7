"""고용24 공통코드 (2026-11-20 응답 확인).

- 지역 코드 CMCD_1: `cmcdRegion > oneDepth{regionCd, regionNm} > twoDepth{regionCd, regionNm, superCd}`.
  시·도는 `11000`처럼 다섯 자리, 시·군·구는 `11110`이다. 이름은 "서울 종로구"처럼 시·도 이름이 앞에 붙어 온다.
  세종은 시·군·구 없이 `36110` 하나로 온다.
- 직종 코드 CMCD_2: `cmcdJobs > oneDepth{jobsCd, jobsNm} > twoDepth{…} > threeDepth{jobsCd, jobsNm, superCd}`.
  대분류 2자리, 중분류 3자리, 세분류 6자리다.

정규화는 지역 표를 시·군·구 이름(label)과 코드 확인에 쓴다. 직종 표는 수집 실행기의 직종 코드 시드 모양
(`{"세분류 코드": {"name", "middle", "major"}}`)으로 바꿔 둔다.
"""

from collections.abc import Mapping
from typing import Any

from .http import as_list, parse_body

NO_REGION_CODE = "00000"  # "지역무관"


def _text(node: Mapping, key: str) -> str:
    value = node.get(key)
    return value.strip() if isinstance(value, str) else ""


def region_names(body: bytes | Mapping) -> dict[str, str]:
    """CMCD_1 → {지역 코드 5자리: 이름}. 시·도(`26000`: "부산")와 시·군·구(`26350`: "부산 해운대구")가 함께 든다.

    "지역무관"(00000)은 넣지 않는다. 응답을 해석하지 못하면 `http.FetchError`.
    """
    parsed = parse_body(body) if isinstance(body, bytes) else body
    root = parsed.get("cmcdRegion") if isinstance(parsed, Mapping) else None
    out: dict[str, str] = {}
    for one in as_list((root or {}).get("oneDepth")):
        if not isinstance(one, Mapping):
            continue
        code, name = _text(one, "regionCd"), _text(one, "regionNm")
        if code and name and code != NO_REGION_CODE:
            out[code] = name
        for two in as_list(one.get("twoDepth")):
            if isinstance(two, Mapping) and _text(two, "regionCd") and _text(two, "regionNm"):
                out[_text(two, "regionCd")] = _text(two, "regionNm")
    return out


def sido_names(names: Mapping[str, str]) -> dict[str, str]:
    """지역 표에서 시·도만 뽑는다. {시·도 2자리: 이름}. 세종처럼 `36110`으로 오는 곳도 앞 2자리로 둔다."""
    out: dict[str, str] = {}
    for code, name in names.items():
        if len(code) == 5 and code.endswith("000"):
            out[code[:2]] = name
    for code, name in names.items():  # 시·도 코드 없이 시·군·구 하나로만 오는 곳 (세종 36110)
        out.setdefault(code[:2], name.split()[0])
    return out


def job_codes(body: bytes | Mapping) -> dict[str, dict[str, Any]]:
    """CMCD_2 → {세분류 코드: {"name", "middle", "major"}}. 수집 실행기의 직종 코드 시드와 같은 모양이다."""
    parsed = parse_body(body) if isinstance(body, bytes) else body
    root = parsed.get("cmcdJobs") if isinstance(parsed, Mapping) else None
    out: dict[str, dict[str, Any]] = {}
    for one in as_list((root or {}).get("oneDepth")):
        if not isinstance(one, Mapping):
            continue
        major = _text(one, "jobsNm") or None
        for two in as_list(one.get("twoDepth")):
            if not isinstance(two, Mapping):
                continue
            middle = _text(two, "jobsNm") or None
            for three in as_list(two.get("threeDepth")):
                if isinstance(three, Mapping) and _text(three, "jobsCd") and _text(three, "jobsNm"):
                    out[_text(three, "jobsCd")] = {"name": _text(three, "jobsNm"), "middle": middle, "major": major}
    return out
