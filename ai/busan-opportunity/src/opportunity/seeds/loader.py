"""JSON 시드 로더. 직접 정리한 기업·정책·지역 통계를 모델로 바꾼다.

`source`나 `asOf`가 없는 항목은 거부하고 어떤 항목인지 알려 준다 (개발계획서2 §3.3).
정책 시드의 `verified`는 파일에 적힌 값 그대로 둔다. 로더가 true로 바꾸지 않는다.
실제 시드 파일은 여기에 없다. 원문을 확인해 만든 파일만 넣는다.

파일 모양
- 기업·정책: 항목 배열이거나 `{"items": [...]}`. 항목은 `CompanyRecord`·`Policy`의 JSON(카멜 표기)과 같다.
- 지역 통계: `{"rent": {지역코드: 항목}, "commute": {지역코드: 항목}}`. 항목 배열도 받는다(`regionCode` 필요).
"""

import json
from collections.abc import Mapping
from os import PathLike
from typing import Any

from pydantic import ValidationError

from ..models.policy import Policy
from ..models.posting import CompanyRecord
from ..models.region import CommuteStat, RegionStats, RentStat


class SeedError(ValueError):
    """시드 파일을 받아들이지 않는다. 메시지에 문제가 있는 항목을 모두 적는다."""

    def __init__(self, path: str, problems: list[str]):
        self.path = path
        self.problems = problems
        super().__init__(f"{path}: 시드 {len(problems)}건 거부\n" + "\n".join(f"- {p}" for p in problems))


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _read(path: str | PathLike) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise SeedError(str(path), [f"파일을 읽지 못했다 ({type(e).__name__})"]) from None
    except json.JSONDecodeError as e:
        raise SeedError(str(path), [f"JSON이 올바르지 않다 ({e.msg}, {e.lineno}행)"]) from None


def _items(path: str | PathLike, data: Any) -> list:
    rows = data.get("items") if isinstance(data, Mapping) else data
    if not isinstance(rows, list):
        raise SeedError(str(path), ["항목 배열(또는 {\"items\": [...]})이어야 한다"])
    return rows


def _name(row: Any, index: int, *id_keys: str) -> str:
    """오류에 쓸 항목 이름. 이름이 없으면 순번만 쓴다."""
    if isinstance(row, Mapping):
        for key in id_keys:
            if not _blank(row.get(key)):
                return f"#{index} {row[key]}"
    return f"#{index}"


def _missing(row: Mapping, *keys: str) -> list[str]:
    return [k for k in keys if _blank(row.get(k))]


def _load_models(path: str | PathLike, model, id_keys: tuple[str, ...], required: tuple[str, ...],
                 nested: tuple[str, ...] = ()) -> list:
    """항목마다 필수 키(source·asOf)를 확인한 뒤 모델로 바꾼다. 문제는 모아서 한꺼번에 알린다."""
    out, problems = [], []
    for index, row in enumerate(_items(path, _read(path))):
        label = _name(row, index, *id_keys)
        if not isinstance(row, Mapping):
            problems.append(f"{label}: 항목이 객체가 아니다")
            continue
        missing = _missing(row, *required)
        for key in nested:  # 배지처럼 출처가 따로 붙는 하위 항목
            for sub in row.get(key) or []:
                if isinstance(sub, Mapping) and _missing(sub, "source", "asOf"):
                    missing.append(f"{key}[{sub.get('label', '?')}].source/asOf")
        if missing:
            problems.append(f"{label}: {', '.join(missing)} 없음")
            continue
        try:
            out.append(model.model_validate(row))
        except ValidationError as e:
            fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
            problems.append(f"{label}: 형식이 맞지 않는다 ({fields})")
    if problems:
        raise SeedError(str(path), problems)
    return out


def load_companies(path: str | PathLike) -> list[CompanyRecord]:
    """청끌기업·강소기업·이전기관 시드. 항목과 배지(`highlights`) 모두 `source`·`asOf`가 있어야 한다."""
    return _load_models(path, CompanyRecord, ("companyId", "name"), ("source", "asOf"), nested=("highlights",))


def load_policies(path: str | PathLike) -> list[Policy]:
    """정책 시드. `verified`와 `verifiedBy`는 파일 값 그대로 둔다."""
    return _load_models(path, Policy, ("policyId", "title"), ("source", "asOf"))


def load_region_stats(path: str | PathLike) -> RegionStats:
    """구별 월세·통근 통계. 항목마다 `source`·`asOf`가 있어야 한다."""
    data = _read(path)
    if not isinstance(data, Mapping):
        raise SeedError(str(path), ["{\"rent\": ..., \"commute\": ...} 객체여야 한다"])
    problems: list[str] = []
    parsed: dict[str, dict] = {"rent": {}, "commute": {}}
    for section, model in (("rent", RentStat), ("commute", CommuteStat)):
        rows = data.get(section) or {}
        if isinstance(rows, list):
            rows = {str(r.get("regionCode", f"#{i}")): r for i, r in enumerate(rows) if isinstance(r, Mapping)}
        for code, row in rows.items():
            label = f"{section}[{code}]"
            if not isinstance(row, Mapping):
                problems.append(f"{label}: 항목이 객체가 아니다")
                continue
            missing = _missing(row, "source", "asOf")
            if missing:
                problems.append(f"{label}: {', '.join(missing)} 없음")
                continue
            try:
                parsed[section][str(code)] = model.model_validate({"regionCode": str(code), **row})
            except ValidationError as e:
                fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
                problems.append(f"{label}: 형식이 맞지 않는다 ({fields})")
    if problems:
        raise SeedError(str(path), problems)
    return RegionStats(rent=parsed["rent"], commute=parsed["commute"])
