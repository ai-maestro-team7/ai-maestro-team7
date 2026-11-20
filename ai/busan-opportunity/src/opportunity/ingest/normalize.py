"""원본 레코드 → `PostingSnapshot`·`Policy`.

원본 필드 이름은 `field_maps.py`의 매핑표만 본다. 여기서는 필드 이름을 박지 않는다.
API에 값이 없으면 만들지 않고 비워 두거나 "확인 필요" 상태로 둔다 (제품 원칙 1·5).
"""

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from ..core import clock
from ..core.regions import SIDO_NAMES
from ..models.enums import (
    BadgeType,
    CareerType,
    EducationLevel,
    EmploymentType,
    ExtractedBy,
    ExtractStatus,
    MoneyUnit,
    OrgType,
    PeriodType,
    PolicyKind,
    PolicySource,
    PolicyStage,
    PostingSource,
    RegionScope,
    Selection,
    SourceType,
)
from ..models.policy import (
    ALWAYS_APPLY_END,
    IncomeRule,
    Policy,
    PolicyApplication,
    PolicyBenefit,
    PolicyEligibility,
    PolicyRegion,
)
from ..models.posting import (
    ROLLING_CLOSES_AT,
    Badge,
    Company,
    CompanyRecord,
    Job,
    PostingSnapshot,
    Salary,
    WorkRegion,
)
from . import codes
from .field_maps import (
    AGE_ONLY_WHEN_LIMIT_FLAG_Y,
    ALIO,
    APPLY_PERIOD_ALWAYS,
    BLANK_CONDITION_TEXTS,
    CATEGORY_MAP,
    COMPANY_ID_PREFIX,
    EXTRA_SIDO_NAMES,
    GANGSO_BADGE_SOURCE,
    INCOME_AMOUNT,
    INCOME_AMOUNT_UNIT_LABEL,
    INCOME_OTHER,
    NATIONAL_MIN_SIDO,
    SIDO_ALIASES,
    STAGE_BY_CATEGORY,
    STAGE_BY_SUBCATEGORY,
    WORK24,
    WORK24_GANGSO,
    YOUTHCENTER,
)
from .http import walk

POSTING_ID_PREFIX = {"work24": "wk24", "alio": "alio"}
POLICY_ID_PREFIX = "ythc"
VERIFIED_BY_YOUTHCENTER = "YOUTHCENTER_API"
MULTI_REGION_LABEL = "근무지 여러 곳 · 공고문 확인"

_ROLLING_WORDS = ("채용시", "상시", "수시", "충원시")
_DATE = re.compile(r"(\d{4})\s*[-./]?\s*(\d{1,2})\s*[-./]?\s*(\d{1,2})")
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(억|만\s*원|만|원)")
_BARE_NUMBERS = re.compile(r"[\d,.\s~\-–]+")
_ZIP_PREFIX = re.compile(r"^\(?\d{5}\)?\s*")
_EDUCATION_ORDER = [EducationLevel.NONE, EducationLevel.HIGH_SCHOOL, EducationLevel.ASSOCIATE,
                    EducationLevel.BACHELOR, EducationLevel.MASTER, EducationLevel.DOCTOR]
_BARE_WON_THRESHOLD = 100_000  # 단위 없는 숫자가 이보다 크면 원, 작으면 만 원으로 본다


class SkipRecord(Exception):
    """이 레코드는 정규화하지 않는다. reason은 런 리포트에 건수로 남는다."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------- 값 꺼내기
def text_of(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(t for t in (text_of(v) for v in value) if t)
    return str(value).strip()


def pick(record: Mapping, spec: str | tuple[str, ...] | None) -> str:
    """매핑표의 값(키 하나 또는 후보 튜플)으로 레코드에서 첫 비어 있지 않은 값을 꺼낸다."""
    if spec is None:
        return ""
    for key in (spec if isinstance(spec, tuple) else (spec,)):
        found = text_of(record.get(key) if key in record else walk(record, key))
        if found:
            return found
    return ""


def clean_id(raw: str) -> str | None:
    """주소와 키를 깨뜨릴 수 있는 ID는 버린다. `#`이 들어가면 요청이 깨진다 (db-schema §2.2)."""
    value = raw.strip()
    if not value or "#" in value or any(ch.isspace() for ch in value):
        return None
    return value


def http_url(raw: str) -> str | None:
    return raw if raw.lower().startswith(("http://", "https://")) else None


def split_items(raw: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n\r,;→>]+", raw) if part.strip()]


# ---------------------------------------------------------------- 날짜·급여
def _to_date(year: str, month: str, day_: str) -> str | None:
    try:
        return date(int(year), int(month), int(day_)).isoformat()
    except ValueError:
        return None


def find_dates(raw: str) -> list[str]:
    return [d for d in (_to_date(*m.groups()) for m in _DATE.finditer(raw)) if d]


def parse_closes(raw: str) -> tuple[str | None, bool]:
    """(closesAt, rolling). 날짜가 있으면 날짜가 우선이다. 날짜도 상시 표현도 없으면 (None, False)."""
    dates = find_dates(raw)
    if dates:
        return dates[0], False
    if any(word in raw.replace(" ", "") for word in _ROLLING_WORDS):
        return ROLLING_CLOSES_AT, True
    return None, False


def _manwon(number: str, unit: str | None) -> float:
    value = float(number.replace(",", ""))
    unit = (unit or "").replace(" ", "")
    if unit == "억":
        return value * 10_000
    if unit in ("만원", "만"):
        return value
    if unit == "원":
        return value / 10_000
    return value / 10_000 if value >= _BARE_WON_THRESHOLD else value


def parse_salary(raw: str, kind: str = "") -> Salary:
    """급여를 만 원/년으로 맞춘다. 회사내규·협의, 시급·일급, 기간을 알 수 없는 값은 disclosed=false다.

    월급은 12를 곱한다. 시급·일급은 근무 시간을 몰라 연봉으로 바꾸지 않는다.
    """
    blob = f"{kind} {raw}"
    compact = blob.replace(" ", "")
    if not raw.strip() or "내규" in compact or "협의" in compact:
        return Salary(disclosed=False)
    if any(word in compact for word in ("시급", "일급", "주급")):
        return Salary(disclosed=False)
    monthly = "월급" in compact or bool(re.search(r"월\s*\d", blob))
    annual = "연봉" in compact or "연간" in compact or bool(re.search(r"연\s*\d", blob))
    if monthly == annual:  # 둘 다이거나 둘 다 아니면 기간을 알 수 없다
        return Salary(disclosed=False)
    matches = _AMOUNT.findall(raw)
    if not matches and _BARE_NUMBERS.fullmatch(raw.strip()):
        matches = [(n, "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", raw)]
    values = [_manwon(n, u) * (12 if monthly else 1) for n, u in matches]
    if not values or len(values) > 2 or any(v <= 0 for v in values):
        return Salary(disclosed=False)
    low, high = round(min(values)), round(max(values))
    if len(values) == 1:
        if "이상" in raw:
            return Salary(disclosed=True, min=low, max=None, unit=MoneyUnit.MANWON_YEAR)
        if "이하" in raw or "까지" in raw:
            return Salary(disclosed=True, min=None, max=high, unit=MoneyUnit.MANWON_YEAR)
    return Salary(disclosed=True, min=low, max=high, unit=MoneyUnit.MANWON_YEAR)


# ---------------------------------------------------------------- 지역
def _sido_of_text(part: str) -> str | None:
    tokens = _ZIP_PREFIX.sub("", part.strip()).split()
    return SIDO_ALIASES.get(tokens[0]) if tokens else None


def _sido_label(sido: str) -> str:
    return SIDO_NAMES.get(sido) or EXTRA_SIDO_NAMES.get(sido) or sido


def _region_label(sido: str, address: str) -> str:
    """"부산 해운대구"처럼 시·도 이름에 이어지는 시·군·구 이름을 붙인다. 주소에 없으면 시·도만 쓴다."""
    tokens = _ZIP_PREFIX.sub("", address.strip()).split()
    names = [_sido_label(sido)]
    if tokens and SIDO_ALIASES.get(tokens[0]) == sido:
        for token in tokens[1:3]:
            if token.endswith(("시", "군", "구")):
                names.append(token)
            else:
                break
    return " ".join(names)


def parse_region(code: str, address: str, *, region_names: Mapping[str, str] | None = None) -> WorkRegion:
    """API 코드 → 주소 글 → 없으면 unknown. 근무지를 모르면 부산으로 세지 않는다 (개발계획서2 §3.2).

    region_names(고용24 지역 표)가 있으면 코드로 찾은 이름("부산 해운대구")을 label로 쓴다.
    """
    digits = re.sub(r"\D", "", code)
    if len(digits) >= 2 and digits[:2] in _sido_codes(region_names):
        sido = digits[:2]
        sigungu = digits[:5] if len(digits) >= 5 and digits[2:5] != "000" else None
        named = (region_names or {}).get(sigungu or f"{sido}000")
        return WorkRegion(sido=sido, sigungu=sigungu, label=named or _region_label(sido, address))
    sidos = {s for s in (_sido_of_text(part) for part in re.split(r"[,;/·]", address)) if s}
    if len(sidos) == 1:
        sido = next(iter(sidos))
        return WorkRegion(sido=sido, label=_region_label(sido, address))
    if len(sidos) > 1:
        return WorkRegion(unknown=True, label=MULTI_REGION_LABEL)
    return WorkRegion(unknown=True)


# ---------------------------------------------------------------- 조건 글
def parse_education(raw: str) -> EducationLevel | None:
    """여러 학력이 적혀 있으면 가장 낮은 것이 최소 학력이다."""
    levels = []
    for part in re.split(r"[,/|·]", raw):
        part = part.replace(" ", "")
        if "박사" in part:
            levels.append(EducationLevel.DOCTOR)
        elif "석사" in part:
            levels.append(EducationLevel.MASTER)
        elif any(w in part for w in ("초대졸", "전문대", "2,3년", "2~3년", "2년제", "3년제")):
            levels.append(EducationLevel.ASSOCIATE)
        elif any(w in part for w in ("대졸", "학사", "4년")):
            levels.append(EducationLevel.BACHELOR)
        elif "고졸" in part:
            levels.append(EducationLevel.HIGH_SCHOOL)
        elif "무관" in part:
            levels.append(EducationLevel.NONE)
    return min(levels, key=_EDUCATION_ORDER.index) if levels else None


def parse_career(raw: str) -> CareerType:
    compact = raw.replace(" ", "")
    has_new, has_exp = "신입" in compact, "경력" in compact
    if (has_new and has_exp) or "무관" in compact:
        return CareerType.ANY
    if has_new:
        return CareerType.NEW
    if has_exp:
        return CareerType.EXPERIENCED
    return CareerType.UNKNOWN


def parse_employment(raw: str) -> EmploymentType:
    """종류가 하나로 정해질 때만 값을 둔다. 여럿이면 UNKNOWN이다."""
    compact = raw.replace(" ", "").replace("무기계약", "")
    found = set()
    if "인턴" in compact:
        found.add(EmploymentType.INTERN)
    if "정규직" in compact:
        found.add(EmploymentType.FULL_TIME)
    if "계약직" in compact or "기간제" in compact:
        found.add(EmploymentType.CONTRACT)
    if any(w in compact for w in ("파트", "시간제", "아르바이트", "시간선택")):
        found.add(EmploymentType.PART_TIME)
    return next(iter(found)) if len(found) == 1 else EmploymentType.UNKNOWN


# ---------------------------------------------------------------- 해시
_HASH_FIELDS = ("title", "organization", "job_description", "closes_at", "official_url",
                "source_type", "source", "company", "org_type", "work_region", "job", "employment_type",
                "career_type", "education_min", "salary", "rolling", "remote_work", "selection_steps", "documents")


def compute_content_hash(snapshot: PostingSnapshot) -> str:
    """내용 필드만으로 만든 sha256. 수집 시각·스냅샷 ID·보강 결과(요건, 배지, 지역인재)는 넣지 않는다."""
    dumped = snapshot.model_dump(mode="json")
    payload = {name: dumped[name] for name in _HASH_FIELDS}
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def snapshot_id_for(as_of, content_hash: str) -> str:
    """`{YYYYMMDD}-{해시 8자}` (db-schema §3)."""
    return f"{clock.day(as_of).replace('-', '')}-{content_hash[:8]}"


# ---------------------------------------------------------------- 공고
def _normalize_posting(spec: dict, record: Mapping, detail: Mapping | None, *, as_of, job_codes: Mapping | None,
                       org_type: OrgType, source: PostingSource) -> PostingSnapshot:
    fields = spec["fields"]
    merged = {**record, **(detail or {})}

    def get(name: str) -> str:
        return pick(merged, fields.get(name))

    raw_id = get("external_id")
    external_id = clean_id(raw_id) if raw_id else None
    if external_id is None:
        raise SkipRecord("missing_id" if not raw_id else "bad_id")
    title, organization = get("title"), get("organization")
    if not title:
        raise SkipRecord("missing_title")
    if not organization:
        raise SkipRecord("missing_organization")
    closes_at, rolling = parse_closes(get("closes_text"))
    if closes_at is None:
        raise SkipRecord("no_deadline")  # 마감을 모르는 공고를 상시 채용으로 보이게 하지 않는다

    region = parse_region(get("region_code"), get("region_text"))
    code = get("job_code")
    coded = (job_codes or {}).get(code, {}) if code else {}
    job_name = get("job_name")
    job = Job(code=code or None, name=job_name or coded.get("name") or title,
              middle=coded.get("middle"), major=coded.get("major"))
    employment = parse_employment(get("employment_text"))
    career = parse_career(get("career_text"))
    education = parse_education(get("education_text"))
    salary = parse_salary(get("salary_text"), get("salary_kind"))
    description = get("description")
    steps, documents = split_items(get("selection_text")), split_items(get("documents_text"))
    url = http_url(get("url"))

    api: dict[str, ExtractedBy] = {"title": ExtractedBy.API, "organization": ExtractedBy.API,
                                   "closesAt": ExtractedBy.API}
    for name, present in (("workRegion", not region.unknown), ("job", bool(job_name or coded)),
                          ("salary", salary.disclosed), ("employmentType", employment != EmploymentType.UNKNOWN),
                          ("careerType", career != CareerType.UNKNOWN), ("educationMin", education is not None),
                          ("jobDescription", bool(description)), ("selectionSteps", bool(steps)),
                          ("documents", bool(documents)), ("officialUrl", url is not None)):
        if present:
            api[name] = ExtractedBy.API

    snapshot = PostingSnapshot(
        job_posting_id=f"{POSTING_ID_PREFIX[spec['source']]}-{external_id}", snapshot_id="pending", title=title,
        organization=organization, job_description=description or None, closes_at=closes_at, official_url=url,
        source_type=SourceType.OFFICIAL, checked_at=clock.iso(clock.parse_as_of(as_of)), source=source,
        company=Company(name=organization), org_type=org_type, work_region=region, job=job,
        employment_type=employment, career_type=career, education_min=education, salary=salary, rolling=rolling,
        selection_steps=steps, documents=documents, extract_status=ExtractStatus.PENDING, extracted_by=api,
        content_hash="pending",
    )
    digest = compute_content_hash(snapshot)
    return snapshot.model_copy(update={"content_hash": digest, "snapshot_id": snapshot_id_for(as_of, digest)})


def normalize_work24(record: Mapping, *, as_of, detail: Mapping | None = None,
                     job_codes: Mapping | None = None) -> PostingSnapshot:
    """고용24 채용정보 → 스냅샷. ID는 `wk24-{구인인증번호}`."""
    return _normalize_posting(WORK24, record, detail, as_of=as_of, job_codes=job_codes,
                              org_type=OrgType.PRIVATE, source=PostingSource.WORK24)


def normalize_alio(record: Mapping, *, as_of, detail: Mapping | None = None,
                   job_codes: Mapping | None = None) -> PostingSnapshot:
    """잡알리오 채용공시 → 스냅샷. ID는 `alio-{공시번호}`."""
    return _normalize_posting(ALIO, record, detail, as_of=as_of, job_codes=job_codes,
                              org_type=OrgType.PUBLIC_INSTITUTION, source=PostingSource.ALIO)


# ---------------------------------------------------------------- 정책 (온통청년)
_YMD = re.compile(r"(\d{4})(\d{2})(\d{2})")
_YMD_RANGE = re.compile(r"(\d{8})\s*~\s*(\d{8})")


def meaningful(raw: str) -> str:
    """자유 서술 값. 비었거나 "-"·"해당 없음" 같은 값이면 빈 글을 돌려준다."""
    text = (raw or "").strip()
    return "" if text in BLANK_CONDITION_TEXTS else text


def _age(raw: str) -> int | None:
    digits = re.sub(r"\D", "", raw)
    value = int(digits) if digits else 0
    return value or None  # 0은 제한 없음


def _ymd(raw: str) -> str | None:
    found = _YMD.fullmatch((raw or "").strip())
    return _to_date(*found.groups()) if found else None


def parse_apply_period(text: str, code: str, biz_start: str, biz_end: str,
                       today: str) -> tuple[str | None, str, PeriodType]:
    """신청 기간 → (applyStart, applyEnd, 기간 종류). 날짜는 YYYY-MM-DD.

    1. aplyYmd에 기간이 있으면 FIXED. 기간이 여럿이면 끝나지 않은 첫 기간, 다 끝났으면 마지막 기간을 쓴다.
    2. 비어 있고 신청기간구분이 상시(추정 0057002)면 ALWAYS, 끝은 9999-12-31.
       사업 기간이 이미 끝났으면 상시라도 지금은 신청할 수 없어 TBD로 둔다.
    3. 그 밖(마감으로 추정되는 0057003, 모르는 코드, 날짜를 못 읽은 경우)은 TBD. 날짜를 만들지 않는다.
    """
    ranges = [(a, b) for a, b in ((_ymd(x), _ymd(y)) for x, y in _YMD_RANGE.findall(text or "")) if a and b]
    if ranges:
        start, end = next(((a, b) for a, b in ranges if b >= today), ranges[-1])
        return start, end, PeriodType.FIXED
    if code == APPLY_PERIOD_ALWAYS:
        ends = _ymd(biz_end)
        if ends is not None and ends < today:
            return None, ALWAYS_APPLY_END, PeriodType.TBD
        return _ymd(biz_start), ALWAYS_APPLY_END, PeriodType.ALWAYS
    return None, ALWAYS_APPLY_END, PeriodType.TBD


def _sido_codes(region_names: Mapping[str, str] | None) -> set[str]:
    known = set(SIDO_NAMES) | set(EXTRA_SIDO_NAMES)
    if region_names:
        known |= set(codes.sido_names(region_names))
    return known


def _unit_of(code: str, present: set[str], region_names: Mapping[str, str] | None) -> str:
    """구가 있는 시의 구 코드(41111 수원시 장안구)는 시 코드(41110)로 묶는다. 시 코드가 목록이나 지역 표에 있을 때만."""
    if code[4] == "0":
        return code
    parent = code[:4] + "0"
    return parent if parent in present or (region_names and parent in region_names) else code


def _only_unit_of_sido(code: str, region_names: Mapping[str, str] | None) -> bool:
    """세종(36110)처럼 시·군·구가 하나뿐인 시·도. 지역 표가 있을 때만 알 수 있다."""
    if not region_names:
        return False
    return [c for c in region_names if c[:2] == code[:2] and not c.endswith("000")] == [code]


def parse_policy_regions(raw: str, *, region_names: Mapping[str, str] | None = None,
                         first_sido: str | None = None) -> list[PolicyRegion]:
    """zipCd(시군구 코드 5자리 목록) → 지역 목록. 알아볼 코드가 하나도 없으면 빈 목록이다.

    - 시·도가 `NATIONAL_MIN_SIDO`곳 이상이면 전국 하나.
    - 한 시·도 안의 시·군·구 하나면 SIGUNGU, 여럿(또는 시·도 전부)이면 SIDO.
    - 여러 시·도에 걸치면 시·도마다 SIDO 하나씩. `first_sido`(부산)가 들어 있으면 맨 앞에 둔다.
      `Policy.region_key()`가 첫 지역만 보기 때문이다.
    """
    known = _sido_codes(region_names)
    found: list[str] = []
    for part in re.split(r"[,\s]+", raw or ""):
        code = re.sub(r"\D", "", part)
        if len(code) == 5 and code[:2] in known and code not in found:
            found.append(code)
    if not found:
        return []
    sidos = sorted({c[:2] for c in found}, key=lambda s: (s != first_sido, s))
    if len(sidos) >= NATIONAL_MIN_SIDO:
        return [PolicyRegion(scope=RegionScope.NATIONAL)]
    if len(sidos) == 1:
        present = set(found)
        units = {_unit_of(c, present, region_names) for c in found}
        if len(units) == 1:
            unit = next(iter(units))
            if not unit.endswith("000") and not _only_unit_of_sido(unit, region_names):
                return [PolicyRegion(scope=RegionScope.SIGUNGU, sido=unit[:2], sigungu=unit)]
    return [PolicyRegion(scope=RegionScope.SIDO, sido=s) for s in sidos]


def _category(raw: str) -> str | None:
    """대분류 → category. "일자리,교육"처럼 여럿이면 표에 있는 첫 이름, 없으면 원문(중복 제거)."""
    parts = list(dict.fromkeys(p.strip() for p in raw.split(",") if p.strip()))
    mapped = [CATEGORY_MAP[p] for p in parts if p in CATEGORY_MAP]
    if mapped:
        return mapped[0]
    return ",".join(parts) or None


def _stage(category: str | None, subcategory: str) -> PolicyStage:
    for part in (p.strip() for p in subcategory.split(",")):
        if part in STAGE_BY_SUBCATEGORY:
            return STAGE_BY_SUBCATEGORY[part]
    return STAGE_BY_CATEGORY.get(category or "", PolicyStage.PREPARE)


def _amount(raw: str) -> int | None:
    digits = re.sub(r"\D", "", raw or "")
    return int(digits) if digits else None


def parse_income(code: str, low: str, high: str, etc: str) -> IncomeRule | None:
    """소득 조건. 판정용 숫자(maxMonthlyIncome 등)는 채우지 않는다. 조건이 있으면 사용자에게 확인을 받는다.

    - 무관(추정 0043001)·빈 코드: 기타 글이 있을 때만 그 글로 조건을 둔다. 없으면 None.
    - 금액(추정 0043002): 금액 범위를 API 값 그대로 글로 적는다. 단위(만 원)는 추정이라 "공고문 확인"을 붙인다.
    - 기타(추정 0043003): 기타 글 원문. 글이 "-"뿐이면 조건이 있다는 것만 적는다.
    """
    note = meaningful(etc)
    if code == INCOME_AMOUNT:
        lo, hi = _amount(low) or 0, _amount(high) or 0
        unit = INCOME_AMOUNT_UNIT_LABEL
        if lo and hi:
            amount = f"소득 {lo:,}~{hi:,}{unit}"
        elif hi:
            amount = f"소득 {hi:,}{unit} 이하"
        elif lo:
            amount = f"소득 {lo:,}{unit} 이상"
        else:
            amount = "소득 조건 있음"
        return IncomeRule(text=f"{note} ({amount} · 공고문 확인)" if note else f"{amount} · 공고문 확인")
    if code == INCOME_OTHER:
        return IncomeRule(text=note or "소득 조건 있음 · 공고문 확인")
    return IncomeRule(text=note) if note else None


def _first_url(record: Mapping, spec) -> str | None:
    for key in _spec_keys(spec):
        url = http_url(text_of(record.get(key)))
        if url:
            return url
    return None


def normalize_youthcenter(record: Mapping, *, as_of, region_names: Mapping[str, str] | None = None,
                          first_sido: str | None = None) -> Policy:
    """온통청년 정책 → `Policy`. ID는 `ythc-{정책번호}`, 공식 API 값이라 verified=true다.

    - 금액(amountMax, publicShareMax)은 글에서 숫자를 뽑아 만들지 않는다. 지원 내용 원문을 summary·benefit에 둔다.
    - 나이는 0이 아닌 값만 쓴다. 나이 제한 여부 값을 믿을 수 없어서다 (`field_maps.AGE_ONLY_WHEN_LIMIT_FLAG_Y`).
    - 취업 상태 조건(jobCd)은 코드 뜻을 몰라 만들지 않는다 (None = 제한 없음).
    - region_names(고용24 지역 표)가 있으면 구 단위 묶기와 시·도 확인에 쓴다. first_sido는 부산 시·도 코드다.
    """
    fields = YOUTHCENTER["fields"]

    def get(name: str) -> str:
        return pick(record, fields.get(name))

    raw_id = get("external_id")
    external_id = clean_id(raw_id) if raw_id else None
    if external_id is None:
        raise SkipRecord("missing_id" if not raw_id else "bad_id")
    title = get("title")
    if not title:
        raise SkipRecord("missing_title")
    regions = parse_policy_regions(get("region_codes"), region_names=region_names, first_sido=first_sido)
    if not regions:
        raise SkipRecord("missing_region")  # 지역을 모르는 정책을 전국 정책으로 만들지 않는다
    when = clock.parse_as_of(as_of)
    today = clock.day(when)

    apply_start, apply_end, period_type = parse_apply_period(
        get("apply_period_text"), get("apply_period_code"), get("biz_start"), get("biz_end"), today)
    limited = get("age_limited").upper() == "Y" or not AGE_ONLY_WHEN_LIMIT_FLAG_Y
    age_min = _age(get("age_min")) if limited else None
    age_max = _age(get("age_max")) if limited else None
    category = _category(get("category"))
    income = parse_income(get("income_code"), get("income_min"), get("income_max"), get("income_text"))
    checks = [meaningful(get("extra_conditions"))]
    excluded = meaningful(get("excluded_targets"))
    checks.append(f"참여 제한 대상: {excluded}" if excluded else "")
    documents = meaningful(get("documents"))
    benefit_text = meaningful(get("benefit_text"))
    selection = Selection.FIRST_COME if get("first_come").upper() == "Y" else Selection.REVIEW

    return Policy(
        policy_id=f"{POLICY_ID_PREFIX}-{external_id}", kind=PolicyKind.POLICY, title=title,
        summary=meaningful(get("summary")) or None, amount_max=None, age_min=age_min, age_max=age_max,
        income_rule=income.text if income else None, apply_start=apply_start, apply_end=apply_end,
        url=_first_url(record, fields.get("url")), source=PolicySource.YOUTHCENTER, as_of=today,
        regions=regions, category=category, stage=_stage(category, get("subcategory")),
        eligibility=PolicyEligibility(age_min=age_min, age_max=age_max, employment=None, income=income,
                                      manual_checks=[c for c in checks if c]),
        benefit=PolicyBenefit(text=benefit_text) if benefit_text else None,
        application=PolicyApplication(period_type=period_type, selection=selection),
        checklist=[f"제출 서류: {documents}"] if documents else [],
        verified=True, verified_by=VERIFIED_BY_YOUTHCENTER, verified_at=clock.iso(when), youthcenter_id=external_id,
    )


def _spec_keys(spec) -> tuple[str, ...]:
    if spec is None:
        return ()
    return spec if isinstance(spec, tuple) else (spec,)


# ---------------------------------------------------------------- 기업 (강소기업)
def normalize_gangso(record: Mapping, *, as_of) -> CompanyRecord:
    """고용24 청년일자리강소기업 → `CompanyRecord`. ID는 `biz-{사업자번호}`.

    배지 이름은 원문 브랜드 이름(sgBrandNm), 기준일은 선정 연도(selYear)다. 연도가 없으면 배지를 만들지 않는다.
    """
    fields = WORK24_GANGSO["fields"]

    def get(name: str) -> str:
        return pick(record, fields.get(name))

    biz_no = re.sub(r"\D", "", get("biz_no"))
    if not biz_no:
        raise SkipRecord("missing_biz_no")
    name = get("name")
    if not name:
        raise SkipRecord("missing_name")
    region = re.sub(r"\D", "", get("region_code"))
    sido = region[:2] if len(region) >= 2 and region[:2] in _sido_codes(None) else None
    year, brand = get("year"), get("brand")
    badges = []
    if re.fullmatch(r"\d{4}", year) and brand:
        badges.append(Badge(type=BadgeType.GANGSO, label=brand, source=GANGSO_BADGE_SOURCE, as_of=year))
    workers = _amount(get("workers"))
    return CompanyRecord(
        company_id=f"{COMPANY_ID_PREFIX}-{biz_no}", name=name, biz_no=biz_no, sido=sido,
        industry=get("industry") or None, size=f"상시근로자 {workers:,}명" if workers is not None else None,
        highlights=badges, source=GANGSO_BADGE_SOURCE, as_of=clock.day(as_of),
    )
