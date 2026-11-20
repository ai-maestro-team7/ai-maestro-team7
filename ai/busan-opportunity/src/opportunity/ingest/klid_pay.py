"""지방출자·출연기관 직원평균임금 (B-D11). 행정안전부 공공데이터 파일을 시드로 바꿔 두고, 배치가 `ORGPAY`에 쓴다.

파일(XLSX)은 연도마다 시트가 하나다. 금액은 원 단위 1인당 평균임금이고 0은 값이 없다는 뜻이다. 런타임에는
엑셀을 읽지 않는다. 저장소에 둔 `seeds/klid_org_pay.json`만 읽는다.

시드 다시 만들기 (openpyxl 필요):
    uv run --no-project --with openpyxl --with pydantic python -m opportunity.ingest.klid_pay <파일.xlsx> \
        src/opportunity/seeds/klid_org_pay.json
"""

import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

from ..models.posting import OrgPay, OrgPayYear
from .field_maps import KLID_PAY, KLID_PAY_SOURCE

SEED_PATH = Path(__file__).resolve().parent.parent / "seeds" / KLID_PAY["seed"]
_KIND = {"출연기관": "지방출연기관", "출자기관": "지방출자기관"}


def org_id(founder: str, name: str) -> str:
    """설립 지자체와 기관 이름으로 만든 ID. 알리오 코드(C0072)와 겹치지 않게 `klid-`를 붙인다."""
    return "klid-" + hashlib.sha256(f"{founder}\x1f{name}".encode("utf-8")).hexdigest()[:10]


def _int(value) -> int:
    try:
        return int(round(float(value or 0)))
    except (TypeError, ValueError):
        return 0


def org_pays_from_sheets(sheets: Mapping[int, Sequence[Sequence]]) -> list[OrgPay]:
    """{연도: [머리줄, 행…]} → 기관별 `OrgPay`. 평균임금이 없거나 `min_plausible`보다 낮은 해는 뺀다.
    남는 해가 없는 기관과 시험용 줄은 뺀다."""
    cols = KLID_PAY["columns"]
    by_org: dict[str, dict] = {}
    for year in sorted(sheets):
        rows = list(sheets[year])
        if not rows:
            continue
        index = {str(h).strip(): i for i, h in enumerate(rows[0]) if h is not None}
        for row in rows[1:]:
            get = (lambda key: row[index[cols[key]]] if cols[key] in index and index[cols[key]] < len(row) else None)
            name, founder = str(get("name") or "").strip(), str(get("founder") or "").strip()
            won = _int(get("average"))
            if not name or any(word in name for word in KLID_PAY["skip_name_words"]):
                continue
            if round(won / 10000) < KLID_PAY["min_plausible"]:  # 0(값 없음)과 믿기 어려운 값은 그해만 뺀다
                continue
            org = by_org.setdefault(org_id(founder, name), {"name": name, "founder": founder, "years": {}, "tenure": {}})
            org["kind"] = _KIND.get(str(get("kind") or "").strip(), str(get("kind") or "").strip() or None)
            org["years"][year] = round(won / 10000)  # 원 → 만 원
            months = _int(get("tenure_years")) * 12 + _int(get("tenure_months"))
            if months:
                org["tenure"][year] = months
    out = []
    for oid, org in sorted(by_org.items(), key=lambda kv: (kv[1]["founder"], kv[1]["name"])):
        latest = max(org["years"])
        out.append(OrgPay(org_id=oid, name=org["name"], org_type=org.get("kind"), ministry=org["founder"] or None,
                          years=[OrgPayYear(year=y, average=v) for y, v in sorted(org["years"].items())],
                          latest_year=latest, latest_average=org["years"][latest], year_note="",
                          tenure_months=org["tenure"].get(latest), source=KLID_PAY_SOURCE,
                          as_of=KLID_PAY["as_of"], source_url=KLID_PAY["page_url"]))
    return out


def load_seed(path: Path = SEED_PATH) -> list[OrgPay]:
    """저장소 시드를 읽어 `OrgPay`로 펼친다. 없으면 빈 목록.

    시드 모양: {"source", "asOf", "sourceUrl", "orgs": [[orgId, 이름, 기관유형, 설립지자체, {연도: 만 원}, 근속 개월], …]}
    """
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out = []
    for oid, name, kind, founder, years, tenure in data["orgs"]:
        by_year = {int(y): int(v) for y, v in years.items()}
        latest = max(by_year)
        out.append(OrgPay(org_id=oid, name=name, org_type=kind, ministry=founder,
                          years=[OrgPayYear(year=y, average=v) for y, v in sorted(by_year.items())],
                          latest_year=latest, latest_average=by_year[latest], year_note="", tenure_months=tenure,
                          source=data["source"], as_of=data["asOf"], source_url=data["sourceUrl"]))
    return out


def write_seed(pays: Iterable[OrgPay], path: Path) -> int:
    """기관마다 한 줄로 쓴다. 출처·기준일·주소는 한 번만 둔다."""
    rows = [[p.org_id, p.name, p.org_type, p.ministry, {str(y.year): y.average for y in p.years}, p.tenure_months]
            for p in pays]
    head = {"source": KLID_PAY_SOURCE, "asOf": KLID_PAY["as_of"], "sourceUrl": KLID_PAY["page_url"]}
    body = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows)
    text = json.dumps(head, ensure_ascii=False)[:-1] + ', "orgs": [\n' + body + "\n]}\n"
    path.write_text(text, encoding="utf-8")
    return len(rows)


def _read_xlsx(path: str) -> dict[int, list[tuple]]:
    import openpyxl  # 시드를 만들 때만 쓴다. Lambda 의존성에 넣지 않는다

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return {int(ws.title): list(ws.iter_rows(values_only=True)) for ws in book.worksheets if ws.title.strip().isdigit()}


if __name__ == "__main__":  # pragma: no cover - 사람이 시드를 다시 만들 때만 돌린다
    src, dst = sys.argv[1], Path(sys.argv[2])
    print(write_seed(org_pays_from_sheets(_read_xlsx(src)), dst), "기관")
