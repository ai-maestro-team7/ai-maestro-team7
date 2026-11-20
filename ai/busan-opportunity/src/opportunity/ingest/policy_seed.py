"""부산 정책 보강 시드. 온통청년 정책에 공식 공고문에서 확인한 값을 덧붙인다.

온통청년 API에는 금액 필드, 경쟁률, 중복 불가 사업, 시 지원분과 본인 저축분 구분이 없다.
`seeds/busan_policies_seed.json`에 공고문에서 옮겨 적은 값만 두고, 수집한 정책에 덧씌운다.

시드 항목
- 찾는 키: `youthcenterId`(온통청년 정책 번호) 또는 `policyId`. youthcenterId로 먼저 찾고 없으면 policyId로 찾는다.
- 출처: `source`(공고문 이름), `sourceUrl`, `asOf`(공고 기준일)는 꼭 있어야 한다. `references`는 참고 주소 목록이다.
- 검수: `verified`, `verifiedBy`, `verifiedAt`.
- 나머지 키는 `Policy` 필드(카멜 표기)다. 적힌 필드만 덮어쓰고 적히지 않은 필드는 온통청년 값을 그대로 둔다.
  하위 객체(benefit, application, eligibility …)는 키 단위로 합친다. 목록은 온통청년 값 뒤에 시드 값을 겹치지 않게 붙인다.
- `title`은 항목 이름표다. 보강할 때는 온통청년 제목을 바꾸지 않고, 새로 만들 때만 쓴다.

보강한 정책은 `source`를 YOUTHCENTER로 두고 `verifiedBy`에 공고문 대조 사실을 남긴다.
온통청년에 없고 `policyId`가 `seed-`로 시작하는 항목은 새 정책(source=BUSAN_SEED)으로 만든다.
둘 다 아니면 못 찾은 항목으로 요약에 남긴다.

CLI
    python -m opportunity.ingest.policy_seed --normalized policies.jsonl --out policies_seeded.jsonl
"""

import argparse
import json
import sys
from collections.abc import Mapping
from os import PathLike
from pathlib import Path
from typing import Any, get_args

from pydantic import BaseModel, ValidationError

from ..core import clock
from ..core.copy_rules import find_forbidden
from ..models.enums import PolicySource
from ..models.policy import Policy
from ..seeds.loader import SeedError

DEFAULT_SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / "busan_policies_seed.json"
SEED_ID_PREFIX = "seed-"
VERIFIED_BY_SEED = "공식 공고문 대조"

# Policy 필드가 아닌 시드 전용 키
_REQUIRED = ("source", "sourceUrl", "asOf")
_META = frozenset({*_REQUIRED, "references", "youthcenterId", "policyId", "verified", "verifiedBy", "verifiedAt"})
_KEEP_ON_ENRICH = frozenset({"title"})  # 보강할 때 온통청년 값을 바꾸지 않는 필드
_TEXT_KEYS = ("summary", "text", "manualChecks", "checklist", "lastCompetition", "expected")


# ---------------------------------------------------------------- 시드 읽기
def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _model_of(annotation: Any) -> type[BaseModel] | None:
    """필드 타입에서 하위 모델을 꺼낸다 (`PolicyBenefit | None` → PolicyBenefit)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    for arg in get_args(annotation):
        found = _model_of(arg)
        if found is not None:
            return found
    return None


def _aliases(model: type[BaseModel]) -> dict[str, Any]:
    """카멜 키 → 필드 타입."""
    return {(f.alias or name): f.annotation for name, f in model.model_fields.items()}


def _unknown_keys(row: Mapping, model: type[BaseModel], prefix: str = "") -> list[str]:
    """모델에 없는 키. 모델이 extra를 버리므로 오타가 조용히 사라지지 않게 미리 거른다."""
    fields = _aliases(model)
    out = []
    for key, value in row.items():
        if not prefix and key in _META:
            continue
        if key not in fields:
            out.append(prefix + key)
            continue
        sub = _model_of(fields[key])
        if sub is not None and isinstance(value, Mapping):
            out.extend(_unknown_keys(value, sub, f"{prefix}{key}."))
    return out


def _texts(value: Any, key: str = "") -> list[str]:
    """화면에 나갈 수 있는 문구를 모은다 (금지 문구 검사용)."""
    if isinstance(value, Mapping):
        return [t for k, v in value.items() for t in _texts(v, k)]
    if isinstance(value, list):
        return [t for v in value for t in _texts(v, key)]
    if isinstance(value, str) and key in _TEXT_KEYS:
        return [value]
    return []


def _patch(row: Mapping) -> dict:
    return {k: v for k, v in row.items() if k not in _META}


def _check_row(row: Any) -> list[str]:
    if not isinstance(row, Mapping):
        return ["항목이 객체가 아니다"]
    problems = []
    missing = [k for k in _REQUIRED if _blank(row.get(k))]
    if missing:
        problems.append(f"{', '.join(missing)} 없음")
    if _blank(row.get("youthcenterId")) and _blank(row.get("policyId")):
        problems.append("youthcenterId나 policyId가 있어야 한다")
    if row.get("verified") is not True or _blank(row.get("verifiedBy")) or _blank(row.get("verifiedAt")):
        problems.append("verified=true, verifiedBy, verifiedAt이 있어야 한다")
    for key in ("asOf", "verifiedAt"):
        if not _blank(row.get(key)):
            try:
                clock.parse_as_of(row[key])
            except (TypeError, ValueError):
                problems.append(f"{key} 날짜 형식이 아니다")
    unknown = _unknown_keys(row, Policy)
    if unknown:
        problems.append(f"모르는 필드 {', '.join(unknown)}")
    forbidden = sorted({p for text in _texts(_patch(row)) for p in find_forbidden(text)})
    if forbidden:
        problems.append(f"금지 문구 {', '.join(forbidden)}")
    if not problems:  # 값 형식은 빈 정책에 얹어 검사한다
        try:
            _merge_into(Policy(policy_id="check", title="check", source=PolicySource.BUSAN_SEED), row, enrich=True)
        except ValidationError as e:
            fields = ", ".join(".".join(str(p) for p in err["loc"]) for err in e.errors())
            problems.append(f"형식이 맞지 않는다 ({fields})")
    return problems


def _label(row: Any, index: int) -> str:
    if isinstance(row, Mapping):
        for key in ("policyId", "youthcenterId", "title"):
            if not _blank(row.get(key)):
                return f"#{index} {row[key]}"
    return f"#{index}"


def load_policy_seed(path: str | PathLike | None = None) -> list[dict]:
    """보강 시드를 읽는다. 출처(source·sourceUrl·asOf)가 없거나 형식이 틀린 항목이 하나라도 있으면 SeedError."""
    path = Path(path) if path is not None else DEFAULT_SEED_PATH
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise SeedError(str(path), [f"파일을 읽지 못했다 ({type(e).__name__})"]) from None
    except json.JSONDecodeError as e:
        raise SeedError(str(path), [f"JSON이 올바르지 않다 ({e.msg}, {e.lineno}행)"]) from None
    rows = data.get("items") if isinstance(data, Mapping) else data
    if not isinstance(rows, list):
        raise SeedError(str(path), ["항목 배열(또는 {\"items\": [...]})이어야 한다"])
    problems = [f"{_label(row, i)}: {p}" for i, row in enumerate(rows) for p in _check_row(row)]
    if problems:
        raise SeedError(str(path), problems)
    return [dict(row) for row in rows]


# ---------------------------------------------------------------- 보강
def _union(base: list, extra: list) -> list:
    out = list(base)
    for item in extra:
        if item not in out:
            out.append(item)
    return out


def _deep_merge(base: Mapping, patch: Mapping) -> dict:
    out = dict(base)
    for key, value in patch.items():
        current = out.get(key)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            out[key] = _deep_merge(current, value)
        elif isinstance(value, list) and isinstance(current, list):
            out[key] = _union(current, value)
        else:
            out[key] = value
    return out


def _merge_into(policy: Policy, row: Mapping, *, enrich: bool) -> Policy:
    patch = _patch(row)
    if enrich:
        patch = {k: v for k, v in patch.items() if k not in _KEEP_ON_ENRICH}
    merged = _deep_merge(policy.to_api(), patch)
    return Policy.model_validate(merged)


def _verified_note(row: Mapping) -> str:
    return f"{row['verifiedBy']}: {row['source']}"


def _enrich(policy: Policy, row: Mapping) -> Policy:
    merged = _merge_into(policy, row, enrich=True)
    previous = policy.verified_by or str(policy.source)
    note = _verified_note(row)
    verified_by = previous if note in previous else f"{previous} + {note}"  # 다시 덧씌워도 늘어나지 않는다
    return merged.model_copy(update={
        "source": policy.source,  # 온통청년 정책은 YOUTHCENTER 그대로
        "policy_id": policy.policy_id,
        "youthcenter_id": policy.youthcenter_id,
        "verified": True,
        "verified_by": verified_by,
        "verified_at": row["verifiedAt"],
    })


def _create(row: Mapping) -> Policy:
    patch = _patch(row)
    data = {
        **patch,
        "policyId": row["policyId"],
        "youthcenterId": row.get("youthcenterId"),  # 나중에 온통청년에 들어오면 수집 파이프라인이 이 번호로 잇는다
        "source": PolicySource.BUSAN_SEED,
        "asOf": row["asOf"],
        "url": patch.get("url") or row["sourceUrl"],
        "verified": True,
        "verifiedBy": _verified_note(row),
        "verifiedAt": row["verifiedAt"],
    }
    return Policy.model_validate(data)


def _plain(value: str | None) -> str | None:
    return value.removeprefix("ythc-") if value else None


def apply_policy_seed(policies: list[Policy], seed: list[dict]) -> tuple[list[Policy], dict]:
    """온통청년 정책에 시드를 덧씌운다. 원래 순서를 지키고 새 정책은 뒤에 붙인다.

    요약: `{"enriched": n, "created": n, "notFound": n, "enrichedIds": [...], "createdIds": [...], "notFoundItems": [...]}`
    """
    out = list(policies)
    by_youthcenter = {_plain(p.youthcenter_id): i for i, p in enumerate(out) if p.youthcenter_id}
    by_id = {p.policy_id: i for i, p in enumerate(out)}
    enriched, created, not_found = [], [], []
    for row in seed:
        index = by_youthcenter.get(_plain(row.get("youthcenterId")))
        if index is None:
            index = by_id.get(row.get("policyId"))
        if index is not None:
            out[index] = _enrich(out[index], row)
            enriched.append(out[index].policy_id)
            continue
        policy_id = row.get("policyId") or ""
        if policy_id.startswith(SEED_ID_PREFIX) and not _blank(row.get("title")):
            if policy_id in by_id:  # 같은 시드 정책이 이미 있다
                out[by_id[policy_id]] = _create(row)
            else:
                by_id[policy_id] = len(out)
                out.append(_create(row))
            created.append(policy_id)
            continue
        not_found.append(row.get("youthcenterId") or policy_id or row.get("title") or "?")
    summary = {
        "enriched": len(enriched), "created": len(created), "notFound": len(not_found),
        "enrichedIds": enriched, "createdIds": created, "notFoundItems": not_found,
    }
    return out, summary


# ---------------------------------------------------------------- CLI
def _read_jsonl(path: Path) -> list[Policy]:
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(Policy.model_validate(json.loads(line)))
    return out


def _write_jsonl(path: Path, policies: list[Policy]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for policy in policies:
            f.write(json.dumps(policy.to_api(), ensure_ascii=False) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="온통청년 정규화 정책에 부산 정책 보강 시드를 덧씌운다")
    parser.add_argument("--normalized", required=True, type=Path, help="정규화 policies.jsonl")
    parser.add_argument("--out", required=True, type=Path, help="보강본을 쓸 jsonl")
    parser.add_argument("--seed", type=Path, default=None, help="보강 시드 JSON (기본: seeds/busan_policies_seed.json)")
    args = parser.parse_args(argv)
    if args.normalized.resolve() == args.out.resolve():
        parser.error("--out은 --normalized와 다른 파일이어야 한다")
    seed = load_policy_seed(args.seed)
    source = _read_jsonl(args.normalized)
    policies, summary = apply_policy_seed(source, seed)
    _write_jsonl(args.out, policies)
    print(json.dumps({"input": len(source), "output": len(policies), **summary},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
