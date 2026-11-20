"""원본 레코드 → `PostingSnapshot`·`Policy`.

원본 필드 이름은 `field_maps.py`의 매핑표만 본다. 여기서는 필드 이름을 박지 않는다.
API에 값이 없으면 만들지 않고 비워 두거나 "확인 필요" 상태로 둔다 (제품 원칙 1·5).
"""

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from ..core import clock
from ..core.copy_rules import OVERSEAS_LABEL
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
    RuleType,
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
    EligibilityRule,
    Job,
    PostingSnapshot,
    Salary,
    WorkRegion,
)
from . import codes
from .field_maps import (
    AGE_ONLY_WHEN_LIMIT_FLAG_Y,
    ALIO,
    ALIO_CAREER,
    ALIO_EDUCATION,
    ALIO_EMPLOYMENT,
    ALIO_JOB_NAME_SHOWN,
    ALIO_NATIONAL_NAMES,
    ALIO_ROLLING_MIN_DAYS,
    ALIO_ROLLING_TITLE_WORDS,
    ALIO_URL_BLANKS,
    APPLY_PERIOD_ALWAYS,
    BLANK_CONDITION_TEXTS,
    CATEGORY_MAP,
    COMPANY_ID_PREFIX,
    EXTRA_SIDO_NAMES,
    GANGSO_BADGE_SOURCE,
    HASH_ID_LENGTH,
    INCOME_AMOUNT,
    INCOME_AMOUNT_UNIT_LABEL,
    INCOME_OTHER,
    KLID,
    KLID_CAREER,
    KLID_EMPLOYMENT,
    KLID_HEADCOUNT_LABEL,
    KLID_JOB_NAME_BLANKS,
    KLID_MERGED_SIDO,
    KLID_NULL_TEXTS,
    KLID_OPEN_STATUSES,
    KLID_ROLLING_MIN_DAYS,
    KLID_SIDO_ALIASES,
    NATIONAL_MIN_SIDO,
    SIDO_ALIASES,
    STAGE_BY_CATEGORY,
    STAGE_BY_SUBCATEGORY,
    WORK24,
    WORK24_GANGSO,
    WORLDJOB,
    WORLDJOB_BLANK_TEXTS,
    WORLDJOB_CAREER,
    WORLDJOB_DOMESTIC_COUNTRIES,
    WORLDJOB_ROLLING_MIN_DAYS,
    YOUTHCENTER,
)
from .http import walk

POSTING_ID_PREFIX = {"work24": "wk24", "alio": "alio", "klid": "klid", "worldjob": "wj"}
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


# ---------------------------------------------------------------- 공고 (잡알리오)
ALIO_MULTI_REGION_LABEL = "{first} 외 {rest}개 지역"
ALIO_NATIONAL_LABEL = "전국 · 근무지 공고문 확인"
ALIO_OTHER_REGION_LABEL = "{names} · 근무지 공고문 확인"
ALIO_DESCRIPTION_HEADINGS = ("지원 자격", "우대", "전형 절차")
_FILE_NUMBER = re.compile(r"^\s*\d+\s*[.)]\s*")
_FILE_EXTENSION = re.compile(r"\.[A-Za-z0-9]{2,5}$")


def _names(raw: str) -> list[str]:
    """쉼표로 이은 이름 목록. 빈 칸은 버리고 처음 나온 순서대로 중복을 뺀다."""
    return list(dict.fromkeys(part.strip() for part in (raw or "").split(",") if part.strip()))


def _sido_by_name() -> dict[str, str]:
    """시·도 이름 → 코드. 공용 이름표(`core/regions.SIDO_NAMES`)에 2026년 통합 시·도(전남광주)를 더한다."""
    return {name: code for code, name in {**SIDO_NAMES, **EXTRA_SIDO_NAMES}.items()}


def parse_alio_region(raw: str, *, first_sido: str | None = None) -> WorkRegion:
    """잡알리오 근무지 이름 목록 → 근무지 하나. 시·군·구 코드가 없어서 sigungu는 늘 None이다.

    - 한 곳이면 그 시·도. 여러 곳이면 first_sido(부산)가 들어 있을 때 그 시·도, 없으면 첫 지역을 sido로 두고
      label에 "부산 외 3개 지역"처럼 여러 곳임을 적는다. "외 N"에는 시·도가 아닌 이름(해외)도 센다.
    - "전국"이 있으면 근무지를 하나로 정할 수 없어 unknown이다. 시·도 이름이 하나도 없으면(해외) unknown.
    """
    names = _names(raw)
    if not names:
        return WorkRegion(unknown=True)
    if any(name in ALIO_NATIONAL_NAMES for name in names):
        return WorkRegion(unknown=True, label=ALIO_NATIONAL_LABEL)
    by_name = _sido_by_name()
    known = [(name, by_name[name]) for name in names if name in by_name]
    if not known:
        return WorkRegion(unknown=True, label=ALIO_OTHER_REGION_LABEL.format(names=" · ".join(names)))
    first_name, sido = next(((n, c) for n, c in known if c == first_sido), known[0])
    if len(names) == 1:
        return WorkRegion(sido=sido, label=first_name)
    return WorkRegion(sido=sido, label=ALIO_MULTI_REGION_LABEL.format(first=first_name, rest=len(names) - 1))


def parse_alio_employment(raw: str) -> EmploymentType:
    """고용 형태 이름 목록. 모두 같은 종류일 때만 값을 둔다 (무기계약직+비정규직 → CONTRACT, 정규직+비정규직 → UNKNOWN)."""
    found = {ALIO_EMPLOYMENT.get(name.replace(" ", "")) or parse_employment(name) for name in _names(raw)}
    return next(iter(found)) if len(found) == 1 else EmploymentType.UNKNOWN


def parse_alio_career(raw: str) -> CareerType:
    name = (raw or "").replace(" ", "")
    return ALIO_CAREER.get(name) or parse_career(name)


def parse_alio_education(raw: str) -> EducationLevel | None:
    """학력 조건 이름 목록에서 가장 낮은 학력. 표에 없는 이름은 글로 읽는다 (`parse_education`)."""
    levels = [ALIO_EDUCATION.get(name.replace(" ", "")) or parse_education(name) for name in _names(raw)]
    levels = [level for level in levels if level is not None]
    return min(levels, key=_EDUCATION_ORDER.index) if levels else None


def parse_alio_job(ncs_names: str, ncs_codes: str, title: str) -> Job:
    """NCS 분류 이름으로 직무 이름을 만든다. 고용24 직종 코드가 없어서 code·middle은 None이다."""
    names, codes_ = _names(ncs_names), _names(ncs_codes)
    shown = " · ".join(names[:ALIO_JOB_NAME_SHOWN])
    if len(names) > ALIO_JOB_NAME_SHOWN:
        shown += f" 외 {len(names) - ALIO_JOB_NAME_SHOWN}"
    return Job(code=None, middle=None, major=names[0] if names else None, name=shown or title, ncs_codes=codes_)


def alio_url(raw: str) -> str | None:
    """기관 누리집 주소. "없음"·"." 같은 값은 버리고, 앞뒤 공백을 지우고, `www.`로 시작하면 https://를 붙인다."""
    value = (raw or "").strip()
    if not value or value in ALIO_URL_BLANKS or any(ch.isspace() for ch in value):
        return None
    if value.lower().startswith("www."):
        value = "https://" + value
    return http_url(value)


def _paragraph(raw: str) -> str:
    lines = [line.rstrip() for line in (raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return meaningful("\n".join(lines).strip())


def alio_description(qualification: str, preference: str, targets: str, selection: str) -> str | None:
    """지원 자격, 우대, 전형 글을 "[제목]" 아래에 이어 한 글로 만든다. 요건 추출(enrich)이 이 글을 읽는다.

    우대 대상 목록(prefCondCn)이 우대 내용(prefCn)에 그대로 들어 있으면 한 번만 쓴다.
    """
    pref = _paragraph(preference)
    target = _paragraph(targets)
    if target and target not in pref:
        pref = "\n".join(p for p in (f"우대 대상: {target}", pref) if p)
    sections = zip(ALIO_DESCRIPTION_HEADINGS, (_paragraph(qualification), pref, _paragraph(selection)))
    parts = [f"[{heading}]\n{body}" for heading, body in sections if body]
    return "\n\n".join(parts) or None


def alio_documents(files: Any, name_key: str) -> list[str]:
    """첨부 파일 이름 → 서류 이름. 앞 번호("1. ")와 확장자를 뗀다. 상세에만 파일 목록이 온다."""
    rows = [f for f in (files if isinstance(files, list) else []) if isinstance(f, Mapping)]
    rows.sort(key=lambda f: (f.get("sortNo") is None, f.get("sortNo") or 0))
    out: list[str] = []
    for row in rows:
        name = _FILE_EXTENSION.sub("", _FILE_NUMBER.sub("", text_of(row.get(name_key)))).strip()
        if name and name not in out:
            out.append(name)
    return out


def _alio_closes(raw: str) -> str | None:
    return _ymd(raw) or next(iter(find_dates(raw or "")), None)


def _alio_rules(education: EducationLevel | None, education_text: str, career: CareerType,
                career_text: str) -> list[EligibilityRule]:
    """API 값으로 만든 지원 자격 조건 (db-schema §3.2). 경력 연수는 API에 없어서 넣지 않는다."""
    rules = []
    if education is not None:
        rules.append(EligibilityRule(rule_id="rule-edu", type=RuleType.EDUCATION, value=education.value,
                                     source_quote=education_text))
    if career != CareerType.UNKNOWN:
        rules.append(EligibilityRule(rule_id="rule-career", type=RuleType.CAREER, value={"type": career.value},
                                     source_quote=career_text))
    return rules


def normalize_alio(record: Mapping, *, as_of, detail: Mapping | None = None, job_codes: Mapping | None = None,
                   first_sido: str | None = None) -> PostingSnapshot:
    """잡알리오 채용공시 → 스냅샷. ID는 `alio-{recrutPblntSn}`.

    - 근무지는 `parse_alio_region`. first_sido(설정의 부산 시·도 코드)가 여러 근무지 가운데 있으면 그 시·도로 둔다.
    - 급여는 응답에 없어서 disclosed=false. 요건은 비워 두고 extractStatus=PENDING (보강이 뽑는다).
    - rolling은 마감일이 `ALIO_ROLLING_MIN_DAYS`일 넘게 남았거나 제목에 "상시"가 있을 때. closesAt은 원문 날짜 그대로다.
    - job_codes는 쓰지 않는다 (고용24 직종 코드가 없다). 수집 실행기가 출처마다 같은 모양으로 부르려고 받는다.
    """
    fields = ALIO["fields"]
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
    closes_at = _alio_closes(get("closes_ymd"))
    if closes_at is None:
        raise SkipRecord("no_deadline")
    when = clock.parse_as_of(as_of)
    days_left = (date.fromisoformat(closes_at) - when.date()).days
    rolling = days_left > ALIO_ROLLING_MIN_DAYS or any(w in title for w in ALIO_ROLLING_TITLE_WORDS)

    region = parse_alio_region(get("region_names"), first_sido=first_sido)
    job = parse_alio_job(get("ncs_names"), get("ncs_codes"), title)
    employment = parse_alio_employment(get("employment_names"))
    career_text, education_text = get("career_name"), get("education_names")
    career = parse_alio_career(career_text)
    education = parse_alio_education(education_text)
    description = alio_description(get("qualification"), get("preference"), get("preference_targets"),
                                   get("selection"))
    documents = alio_documents(merged.get(fields["files"]), fields["file_name"])
    url = alio_url(get("url"))

    api: dict[str, ExtractedBy] = {"title": ExtractedBy.API, "organization": ExtractedBy.API,
                                   "closesAt": ExtractedBy.API}
    for name, present in (("workRegion", not region.unknown), ("job", job.major is not None),
                          ("employmentType", employment != EmploymentType.UNKNOWN),
                          ("careerType", career != CareerType.UNKNOWN), ("educationMin", education is not None),
                          ("jobDescription", description is not None), ("documents", bool(documents)),
                          ("officialUrl", url is not None)):
        if present:
            api[name] = ExtractedBy.API

    snapshot = PostingSnapshot(
        job_posting_id=f"{POSTING_ID_PREFIX['alio']}-{external_id}", snapshot_id="pending", title=title,
        organization=organization, job_description=description, closes_at=closes_at, official_url=url,
        source_type=SourceType.OFFICIAL, checked_at=clock.iso(when), source=PostingSource.ALIO,
        company=Company(name=organization), org_type=OrgType.PUBLIC_INSTITUTION, work_region=region, job=job,
        employment_type=employment, career_type=career, education_min=education, salary=Salary(disclosed=False),
        rolling=rolling, selection_steps=[], documents=documents,
        eligibility_rules=_alio_rules(education, education_text, career, career_text),
        extract_status=ExtractStatus.PENDING, extracted_by=api, content_hash="pending",
    )
    digest = compute_content_hash(snapshot)
    return snapshot.model_copy(update={"content_hash": digest, "snapshot_id": snapshot_id_for(as_of, digest)})


# ---------------------------------------------------------------- 공고 (지방공공기관)
KLID_DESCRIPTION_HEADINGS = ("모집 개요", "직무 내용", "자격·면허", "우대", "지역 제한", "전형 절차")
KLID_LOCAL_LIMIT = "지역 제한: {name}"
KLID_LOCAL_LIMIT_REASON = "지역 제한: {name} ({reason})"
# "공고문 참조"처럼 내용 없이 공고문을 가리키기만 하는 글. 설명·서류 칸에 넣지 않는다
_SEE_NOTICE = re.compile(r"^[(\[]?\s*(붙임|첨부)?\s*(채용\s*)?(공고\s*(문|서)?|파일|문서)\s*(을|를)?\s*"
                         r"(참조|참고|확인|에\s*의함)\s*[)\]]?\.?$")
_KLID_ADDRESS_PREFIX = re.compile(r"^\s*\(?\s*(우\s*\.?\s*)?\d{5}\s*\)?\s*,?\s*")  # "(우.54853) ", "10400, "
_KLID_SALARY = re.compile(r"^\s*(\d[\d,]*)\s*(억|만)\s*원?\s*(이상|이하)\s*$")


def _klid_text(raw: str) -> str:
    """빈 칸 표시("null", "-")와 공고문 참조 문구를 빈 글로 바꾼다."""
    text = _paragraph(raw)
    if text in KLID_NULL_TEXTS or _SEE_NOTICE.match(text.replace(" ", "")) or _SEE_NOTICE.match(text):
        return ""
    return text


def _sido_alias(name: str) -> str | None:
    key = (name or "").strip()
    return SIDO_ALIASES.get(key) or KLID_SIDO_ALIASES.get(key)


def _sigungu_index(sido: str, region_names: Mapping[str, str] | None) -> dict[str, str]:
    """지역 표에서 한 시·도의 시·군·구 이름 → 코드. "부산 해운대구"는 "해운대구", "경기 수원시 장안구"는 "수원시 장안구"."""
    out: dict[str, str] = {}
    for code, name in (region_names or {}).items():
        if code[:2] != sido or code.endswith("000"):
            continue
        parts = name.split()
        if len(parts) > 1:
            out[" ".join(parts[1:])] = code
    return out


def parse_klid_region(sido_name: str, address: str, *,
                      region_names: Mapping[str, str] | None = None) -> WorkRegion:
    """시·도 이름(SIDO_CD) → 시·도 코드. 주소에 시·군·구가 있으면 지역 표로 sigungu까지 채운다.

    - 시·도 이름을 모르면 unknown이다 (부산으로 세지 않는다).
    - 주소 첫 낱말이 다른 시·도면 시·군·구를 찾지 않는다. 시·도 없이 "안양시 동안구 …"로 시작하면 시·도 안에서 찾는다.
    - 지역 표가 없거나 이름이 맞지 않으면 sigungu는 None이다. 낱말 둘("수원시 장안구")을 하나("수원시")보다 먼저 맞춘다.
    """
    sido = _sido_alias(sido_name)
    if sido is None:
        return WorkRegion(unknown=True)
    tokens = _KLID_ADDRESS_PREFIX.sub("", (address or "").strip()).split()
    address_sido = _sido_alias(tokens[0]) if tokens else None
    if address_sido is not None:
        if KLID_MERGED_SIDO.get(address_sido, address_sido) != sido:
            return WorkRegion(sido=sido, label=_sido_label(sido))
        tokens = tokens[1:]
    units = [c for c in (region_names or {}) if c[:2] == sido and not c.endswith("000")]
    if len(units) == 1:  # 세종(36110)처럼 시·군·구가 하나뿐인 시·도
        return WorkRegion(sido=sido, sigungu=units[0], label=region_names[units[0]])
    index = _sigungu_index(sido, region_names)
    for width in (2, 1):
        name = " ".join(tokens[:width])
        if len(tokens) >= width and name in index:
            code = index[name]
            return WorkRegion(sido=sido, sigungu=code, label=(region_names or {}).get(code) or _sido_label(sido))
    names = [_sido_label(sido)]
    for token in tokens[:2]:
        if token.endswith(("시", "군", "구")):
            names.append(token)
        else:
            break
    return WorkRegion(sido=sido, label=" ".join(names))


def parse_klid_salary(raw: str) -> Salary:
    """연봉 구간 글 → 만 원/년. "N만원 이상"은 min=N, "N만원 이하"는 max=N, "1억원 이상"은 min=10000.

    "무급"이나 읽지 못한 글은 disclosed=false다 (금액을 만들지 않는다).
    """
    found = _KLID_SALARY.match((raw or "").replace(" ", ""))
    if not found:
        return Salary(disclosed=False)
    number, unit, bound = found.groups()
    value = round(_manwon(number, "억" if unit == "억" else "만"))
    if value <= 0:
        return Salary(disclosed=False)
    if bound == "이상":
        return Salary(disclosed=True, min=value, max=None, unit=MoneyUnit.MANWON_YEAR)
    return Salary(disclosed=True, min=None, max=value, unit=MoneyUnit.MANWON_YEAR)


def parse_klid_employment(raw: str) -> EmploymentType:
    name = (raw or "").replace(" ", "")
    return KLID_EMPLOYMENT.get(name, EmploymentType.UNKNOWN)


def parse_klid_career(raw: str) -> CareerType:
    name = (raw or "").replace(" ", "")
    return KLID_CAREER.get(name) or parse_career(name)


def klid_description(get, licenses: list[str], *, opens: str | None, closes: str | None) -> str | None:
    """모집 개요·직무·자격·우대·지역 제한·전형을 "[제목]" 아래에 이어 한 글로 만든다. 값은 원문 그대로다.

    자격·면허는 필수인지 우대인지 응답에서 알 수 없어 지원 자격 조건(eligibilityRules)으로 만들지 않는다.
    지역 제한(LOCAL_YN=Y)도 글로만 둔다. 판정에는 쓰지 않는다.
    """
    overview = []
    kind, field_ = _klid_text(get("org_kind")), _klid_text(get("org_field"))
    if kind:
        overview.append(f"기관 구분: {kind}" + (f" ({field_})" if field_ else ""))
    for label, value in (("모집 분야", _klid_text(get("job_name"))), ("고용 형태", _klid_text(get("employment_name"))),
                         ("직급", _klid_text(get("position"))), ("연봉(원문)", _klid_text(get("salary_text")))):
        if value:
            overview.append(f"{label}: {value}")
    headcount = re.sub(r"\D", "", get("headcount"))
    if headcount and int(headcount) > 0:
        overview.append("모집 인원: " + KLID_HEADCOUNT_LABEL.format(n=int(headcount)))
    if opens or closes:
        overview.append(f"모집 기간: {opens or '확인 필요'} ~ {closes or '확인 필요'}")

    local = ""
    if get("local_yn").upper() == "Y":
        name, reason = _klid_text(get("local_name")), _klid_text(get("local_reason"))
        if name:
            local = (KLID_LOCAL_LIMIT_REASON.format(name=name, reason=reason) if reason
                     else KLID_LOCAL_LIMIT.format(name=name))
    bodies = ("\n".join(overview), _klid_text(get("duty")), "\n".join(licenses), _klid_text(get("special")), local,
              _klid_text(get("selection")))
    parts = [f"[{heading}]\n{body}" for heading, body in zip(KLID_DESCRIPTION_HEADINGS, bodies) if body]
    return "\n\n".join(parts) or None


def _hash_id(parts: list[str]) -> str:
    raw = "\x1f".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:HASH_ID_LENGTH]


def _klid_date(raw: str) -> str | None:
    return next(iter(find_dates(raw or "")), None)


def _finish(snapshot: PostingSnapshot, as_of) -> PostingSnapshot:
    digest = compute_content_hash(snapshot)
    return snapshot.model_copy(update={"content_hash": digest, "snapshot_id": snapshot_id_for(as_of, digest)})


def normalize_klid(record: Mapping, *, as_of, detail: Mapping | None = None, job_codes: Mapping | None = None,
                   region_names: Mapping[str, str] | None = None, hash_id: bool = False) -> PostingSnapshot:
    """지방공공기관 채용정보 → 스냅샷. ID는 `klid-{NO}`. NO가 없거나 hash_id=True면 `klid-h{내용 해시 16자}`.

    - 모집중·모집예정이 아닌 공고는 넣지 않는다 (SkipRecord "closed_status").
    - 근무지는 `parse_klid_region` (시·도 이름 + 기관 주소의 시·군·구). 주소는 기관 주소라서 실제 근무지와 다를 수 있다.
    - 급여는 `parse_klid_salary`. 직무 코드는 없다 (job.code·major는 None).
    - 같은 NO가 내용이 다른 두 공고에 붙어 오면 부르는 쪽이 hash_id=True로 다시 부른다.
    - detail, job_codes는 쓰지 않는다. 수집 실행기가 출처마다 같은 모양으로 부르려고 받는다.
    """
    fields = KLID["fields"]
    merged = {**record, **(detail or {})}

    def get(name: str) -> str:
        value = pick(merged, fields.get(name))
        return "" if value in KLID_NULL_TEXTS else value

    title, organization = get("title"), get("organization")
    if not title:
        raise SkipRecord("missing_title")
    if not organization:
        raise SkipRecord("missing_organization")
    status = get("status").replace(" ", "")
    if status not in KLID_OPEN_STATUSES:
        raise SkipRecord("closed_status")
    closes_at = _klid_date(get("closes_ymd"))
    if closes_at is None:
        raise SkipRecord("no_deadline")
    opens_at = _klid_date(get("opens_ymd"))
    raw_id = get("external_id")
    external_id = None if hash_id else (clean_id(raw_id) if raw_id else None)
    if external_id is None:
        external_id = "h" + _hash_id([organization, title, get("sido_name"), get("job_name"), opens_at or "",
                                      raw_id])
    when = clock.parse_as_of(as_of)
    days_left = (date.fromisoformat(closes_at) - when.date()).days
    rolling = days_left > KLID_ROLLING_MIN_DAYS

    region = parse_klid_region(get("sido_name"), get("work_place") or get("address"), region_names=region_names)
    job_text = get("job_name")
    job = Job(code=None, middle=None, major=None,
              name=job_text if job_text and job_text not in KLID_JOB_NAME_BLANKS else title)
    employment = parse_klid_employment(get("employment_name"))
    career_text = get("career_name")
    career = parse_klid_career(career_text)
    salary = parse_klid_salary(get("salary_text"))
    licenses = list(dict.fromkeys(
        t for t in (_klid_text(text_of(merged.get(key))) for key in fields["licenses"]) if t))
    description = klid_description(get, licenses, opens=opens_at, closes=closes_at)
    documents_text = _klid_text(get("documents_text"))
    documents = [d for d in (_FILE_NUMBER.sub("", item).strip() for item in split_items(documents_text)) if d]
    url = http_url(get("url"))

    api: dict[str, ExtractedBy] = {"title": ExtractedBy.API, "organization": ExtractedBy.API,
                                   "closesAt": ExtractedBy.API}
    for name, present in (("workRegion", not region.unknown), ("job", job_text not in ("", *KLID_JOB_NAME_BLANKS)),
                          ("salary", salary.disclosed), ("employmentType", employment != EmploymentType.UNKNOWN),
                          ("careerType", career != CareerType.UNKNOWN), ("jobDescription", description is not None),
                          ("documents", bool(documents)), ("officialUrl", url is not None)):
        if present:
            api[name] = ExtractedBy.API

    snapshot = PostingSnapshot(
        job_posting_id=f"{POSTING_ID_PREFIX['klid']}-{external_id}", snapshot_id="pending", title=title,
        organization=organization, job_description=description, closes_at=closes_at, official_url=url,
        source_type=SourceType.OFFICIAL, checked_at=clock.iso(when), source=PostingSource.KLID,
        company=Company(name=organization, hq_sido=region.sido), org_type=OrgType.LOCAL_PUBLIC,
        work_region=region, job=job, employment_type=employment, career_type=career, education_min=None,
        salary=salary, rolling=rolling, selection_steps=[], documents=documents,
        eligibility_rules=_alio_rules(None, "", career, career_text),
        extract_status=ExtractStatus.PENDING, extracted_by=api, content_hash="pending",
    )
    return _finish(snapshot, as_of)


# ---------------------------------------------------------------- 공고 (해외취업)
WORLDJOB_DESCRIPTION_LABELS = (("industry", "업종"), ("language", "언어 조건"), ("visa", "비자"),
                               ("headcount", "모집 인원"), ("origin", "공고 출처 기관"))


def _worldjob_text(raw: str) -> str:
    text = (raw or "").strip()
    return "" if text in WORLDJOB_BLANK_TEXTS else text


def parse_worldjob_region(country: str) -> WorkRegion:
    """나라 이름 → 해외 근무지. "대한민국"은 국내 공고인데 시·도가 없어 unknown이다. 나라가 비면 unknown."""
    name = _worldjob_text(country)
    if not name:
        return WorkRegion(unknown=True)
    if name in WORLDJOB_DOMESTIC_COUNTRIES:
        return WorkRegion(unknown=True)
    return WorkRegion(overseas=True, country=name, sido=None, label=OVERSEAS_LABEL.format(country=name))


def worldjob_description(get) -> str | None:
    lines = []
    for name, label in WORLDJOB_DESCRIPTION_LABELS:
        value = _worldjob_text(get(name))
        if name == "headcount":
            digits = re.sub(r"\D", "", value)
            value = KLID_HEADCOUNT_LABEL.format(n=int(digits)) if digits and int(digits) > 0 else ""
        if value:
            lines.append(f"{label}: {value}")
    return "[모집 개요]\n" + "\n".join(lines) if lines else None


def worldjob_id(record: Mapping) -> str:
    """공고 번호가 응답에 없어서 내용 해시로 ID를 만든다. 마감일·언어·비자·인원은 넣지 않는다 (연장돼도 같은 ID)."""
    fields = WORLDJOB["fields"]
    return _hash_id([pick(record, fields[name]) for name in WORLDJOB["id_fields"]])


def normalize_worldjob(record: Mapping, *, as_of, detail: Mapping | None = None,
                       job_codes: Mapping | None = None) -> PostingSnapshot:
    """해외취업 모집공고 → 스냅샷. ID는 `wj-{내용 해시 16자}`.

    - 근무지는 해외(overseas=true, country=나라 이름). 부산·수도권 어느 쪽으로도 세지 않는다.
    - 급여·원문 링크는 응답에 없어 disclosed=false, officialUrl=None이다.
    - 업종·언어·비자·인원·출처 기관은 jobDescription에 원문 그대로 둔다.
    """
    fields = WORLDJOB["fields"]
    merged = {**record, **(detail or {})}

    def get(name: str) -> str:
        return pick(merged, fields.get(name))

    title, organization = get("title"), get("organization")
    if not title:
        raise SkipRecord("missing_title")
    if not organization:
        raise SkipRecord("missing_organization")
    closes_at = next(iter(find_dates(get("closes_ymd"))), None)
    if closes_at is None:
        raise SkipRecord("no_deadline")
    when = clock.parse_as_of(as_of)
    rolling = (date.fromisoformat(closes_at) - when.date()).days > WORLDJOB_ROLLING_MIN_DAYS

    region = parse_worldjob_region(get("country"))
    job_text = get("job_name")
    job = Job(code=None, middle=None, major=None, name=job_text or title)
    career_text = get("career_name")
    career = WORLDJOB_CAREER.get(career_text.replace(" ", "")) or parse_career(career_text)
    description = worldjob_description(get)

    api: dict[str, ExtractedBy] = {"title": ExtractedBy.API, "organization": ExtractedBy.API,
                                   "closesAt": ExtractedBy.API}
    for name, present in (("workRegion", not region.unknown), ("job", bool(job_text)),
                          ("careerType", career != CareerType.UNKNOWN), ("jobDescription", description is not None)):
        if present:
            api[name] = ExtractedBy.API

    snapshot = PostingSnapshot(
        job_posting_id=f"{POSTING_ID_PREFIX['worldjob']}-{worldjob_id(merged)}", snapshot_id="pending",
        title=title, organization=organization, job_description=description, closes_at=closes_at, official_url=None,
        source_type=SourceType.OFFICIAL, checked_at=clock.iso(when), source=PostingSource.WORLDJOB,
        company=Company(name=organization), org_type=OrgType.PRIVATE, work_region=region, job=job,
        employment_type=EmploymentType.UNKNOWN, career_type=career, education_min=None,
        salary=Salary(disclosed=False), rolling=rolling, selection_steps=[], documents=[],
        eligibility_rules=_alio_rules(None, "", career, career_text),
        extract_status=ExtractStatus.PENDING, extracted_by=api, content_hash="pending",
    )
    return _finish(snapshot, as_of)


# ---------------------------------------------------------------- 공고 묶음
@dataclass
class PostingBatch:
    snapshots: dict[str, PostingSnapshot] = field(default_factory=dict)
    records: dict[str, Mapping] = field(default_factory=dict)
    skipped: Counter = field(default_factory=Counter)
    duplicates: int = 0  # 같은 ID, 같은 내용이 두 번 온 건수 (해외취업은 똑같은 행이 온다)
    rehashed: int = 0    # 같은 ID인데 내용이 달라 해시 ID로 바꾼 건수


def normalize_postings(records: Iterable[Mapping], normalize: Callable[..., PostingSnapshot], *,
                       rehash_on_collision: bool = False, **kwargs) -> PostingBatch:
    """레코드마다 정규화한다. 건너뛴 이유는 건수로 센다. 모델 검사에 실패한 레코드는 "invalid_model"로 센다.

    rehash_on_collision=True면 같은 ID에 내용이 다른 레코드가 오면 `hash_id=True`로 다시 정규화한다 (지방공공기관).
    """
    batch = PostingBatch()
    for record in records:
        try:
            snap = normalize(record, **kwargs)
            previous = batch.snapshots.get(snap.job_posting_id)
            if previous is not None and previous.content_hash != snap.content_hash and rehash_on_collision:
                snap = normalize(record, hash_id=True, **kwargs)
                batch.rehashed += 1
        except SkipRecord as e:
            batch.skipped[e.reason] += 1
            continue
        except ValueError:  # pydantic ValidationError는 ValueError다
            batch.skipped["invalid_model"] += 1
            continue
        if snap.job_posting_id in batch.snapshots:
            batch.duplicates += 1
        batch.snapshots[snap.job_posting_id] = snap
        batch.records[snap.job_posting_id] = record
    return batch


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
    # "…신청기업"은 선정이 아니라 신청 상태라 배지로 만들지 않는다 (사실과 다른 인증 표시 금지)
    if re.fullmatch(r"\d{4}", year) and brand and "신청" not in brand:
        badges.append(Badge(type=BadgeType.GANGSO, label=brand, source=GANGSO_BADGE_SOURCE, as_of=year))
    workers = _amount(get("workers"))
    return CompanyRecord(
        company_id=f"{COMPANY_ID_PREFIX}-{biz_no}", name=name, biz_no=biz_no, sido=sido,
        industry=get("industry") or None, size=f"상시근로자 {workers:,}명" if workers is not None else None,
        highlights=badges, source=GANGSO_BADGE_SOURCE, as_of=clock.day(as_of),
    )
