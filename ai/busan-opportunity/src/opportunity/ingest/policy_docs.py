"""정책 검색(RAG)용 문서 만들기. Bedrock Knowledge Base의 데이터 소스(S3 `kb/policies/`)에 올린다.

정책 1건이 문서 1개다: `{policyId}.md`(원문 그대로 이어 붙인 글)와 `{policyId}.md.metadata.json`(걸러 낼 때 쓰는 값).
글은 온통청년 원본 응답에서 가져오고, 요약하거나 고쳐 쓰지 않는다. 담당자 이름과 전화번호는 넣지 않는다.

실행: PYTHONPATH=src python -m opportunity.ingest.policy_docs --raw ~/team07-opp-data/raw --day 2026-11-20 \
        --normalized ~/team07-opp-data/normalized/2026-11-20/policies.jsonl --out ~/team07-opp-data/kb/policies
"""

import argparse
import json
from pathlib import Path

# 문서에 넣는 원본 필드 (제목, 필드 이름). 값이 비었거나 "해당 없음"이면 뺀다
SECTIONS = (
    ("정책 설명", "plcyExplnCn"),
    ("지원 내용", "plcySprtCn"),
    ("추가 신청 자격", "addAplyQlfcCndCn"),
    ("참여 제한 대상", "ptcpPrpTrgtCn"),
    ("소득 조건", "earnEtcCn"),
    ("신청 기간", "aplyYmd"),
    ("신청 방법", "plcyAplyMthdCn"),
    ("심사 방법", "srngMthdCn"),
    ("제출 서류", "sbmsnDcmntCn"),
    ("기타", "etcMttrCn"),
)
EMPTY = {"", "-", "해당 없음", "해당없음", "없음", "null"}
MAX_CHARS = 6000  # 임베딩 모델 입력 한도 안에 두려고 자른다. 자르면 끝에 표시한다


def _clean(value) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    return "" if text in EMPTY else text


def build_document(raw: dict, policy: dict) -> tuple[str, dict]:
    """(문서 글, 메타데이터). raw는 온통청년 원본 한 건, policy는 정규화한 Policy(to_api)다."""
    lines = [f"# {_clean(raw.get('plcyNm'))}", ""]
    category = " > ".join(x for x in (_clean(raw.get("lclsfNm")), _clean(raw.get("mclsfNm"))) if x)
    if category:
        lines.append(f"분류: {category}")
    if _clean(raw.get("sprvsnInstCdNm")):
        lines.append(f"주관 기관: {_clean(raw.get('sprvsnInstCdNm'))}")
    if raw.get("sprtTrgtAgeLmtYn") == "Y" and (policy.get("ageMin") or policy.get("ageMax")):
        lines.append(f"지원 나이: 만 {policy.get('ageMin') or '-'}세 ~ 만 {policy.get('ageMax') or '-'}세")
    for title, key in SECTIONS:
        text = _clean(raw.get(key))
        if text:
            lines += ["", f"## {title}", text]
    url = _clean(raw.get("aplyUrlAddr")) or _clean(raw.get("refUrlAddr1"))
    if url:
        lines += ["", f"신청·참고 주소: {url}"]
    text = "\n".join(lines).strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rstrip() + "\n\n(원문이 길어 뒷부분을 줄였습니다. 원문 주소에서 확인하세요.)"
    regions = policy.get("regions") or []
    first = regions[0] if regions else {}
    metadata = {
        "policyId": policy["policyId"],
        "title": policy["title"],
        "regionKey": _region_key(regions),
        "scope": first.get("scope") or "NATIONAL",
        "sigungu": first.get("sigungu") or "",
        "category": policy.get("category") or "",
        "applyEnd": int((policy.get("applyEnd") or "9999-12-31").replace("-", "")),
        "source": policy.get("source") or "YOUTHCENTER",
        "asOf": policy.get("asOf") or "",
    }
    return text, metadata


def _region_key(regions: list[dict]) -> str:
    for region in regions:
        if region.get("scope") != "NATIONAL" and region.get("sido"):
            return region["sido"]
    return "00"


def build_all(raw_dir: Path, day: str, normalized: Path, out: Path) -> dict:
    policies = {}
    for line in normalized.expanduser().read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        policies[row["policyId"]] = row
    out = out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    written, skipped, chars = 0, 0, 0
    for path in sorted((raw_dir.expanduser() / "youthcenter" / day).glob("policies_p*.json")):
        for raw in json.loads(path.read_text(encoding="utf-8"))["result"]["youthPolicyList"]:
            policy = policies.get(f"ythc-{raw.get('plcyNo')}")
            if policy is None or not policy.get("verified"):
                skipped += 1
                continue
            text, metadata = build_document(raw, policy)
            (out / f"{policy['policyId']}.md").write_text(text + "\n", encoding="utf-8")
            (out / f"{policy['policyId']}.md.metadata.json").write_text(
                json.dumps({"metadataAttributes": metadata}, ensure_ascii=False), encoding="utf-8")
            written += 1
            chars += len(text)
    return {"written": written, "skipped": skipped, "avgChars": round(chars / written) if written else 0}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", required=True, type=Path)
    parser.add_argument("--day", required=True)
    parser.add_argument("--normalized", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build_all(args.raw, args.day, args.normalized, args.out), ensure_ascii=False))


if __name__ == "__main__":
    main()
