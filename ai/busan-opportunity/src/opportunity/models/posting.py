"""공고 모델. `team07-catalog`의 POSTING# 아이템과 같은 모양이다 (`docs/db-schema.md` §3).

- 스냅샷(SNAP#): 내용이 바뀔 때만 새로 쓴다. 상세 화면과 A가 읽는다.
- 최신(LATEST): 목록·피드·대안이 읽는다. 스냅샷을 열지 않고도 점수를 낼 수 있게 목록용 값을 둔다.
- 대안 후보(ALTS): 수집 때 미리 계산한 부산 후보.
"""

from typing import Any

from pydantic import Field

from .base import OppModel
from .enums import (
    BadgeType,
    CareerType,
    CheonggeulType,
    EducationLevel,
    EmploymentType,
    ExtractedBy,
    ExtractStatus,
    MoneyUnit,
    OrgType,
    PostingSource,
    RegionalBenefitKind,
    RegionalTalentStatus,
    RemoteWork,
    RequirementKind,
    RuleType,
    SourceType,
)

ROLLING_CLOSES_AT = "9999-12-31"  # 상시 채용. 정렬 키가 없으면 GSI에서 빠지므로 이 값을 넣는다


class Badge(OppModel):
    """배지에는 출처와 기준일이 꼭 있어야 한다. 없으면 응답에서 뺀다 (T-08)."""

    type: BadgeType
    label: str
    source: str | None = None
    as_of: str | None = None
    cheonggeul_type: CheonggeulType | None = None


class Company(OppModel):
    name: str
    biz_no: str | None = None
    hq_sido: str | None = None  # 본사 소재지. 부산 여부 판단에는 쓰지 않는다


class WorkRegion(OppModel):
    """실제 근무지. 근무지를 모르면 unknown=true이고 부산으로 세지 않는다."""

    sido: str | None = None
    sigungu: str | None = None
    label: str = "근무지 확인 필요"
    unknown: bool = False
    overseas: bool = False       # 해외 근무. 부산·수도권 어느 쪽으로도 세지 않는다
    country: str | None = None   # 해외 근무 국가 이름 (원문)


class Job(OppModel):
    code: str | None = None    # 고용24 직종 코드 (세분류)
    middle: str | None = None  # 중분류
    major: str | None = None   # 대분류
    name: str
    ncs_codes: list[str] = Field(default_factory=list)


class Salary(OppModel):
    """급여는 만 원/년으로 통일한다. '회사내규'는 disclosed=false."""

    disclosed: bool = False
    min: int | None = None
    max: int | None = None
    unit: MoneyUnit = MoneyUnit.MANWON_YEAR


class Requirement(OppModel):
    """공고 요건 (D-10). sourceQuote는 공고 원문에 실제로 있는 문장이어야 한다."""

    requirement_id: str
    name: str
    kind: RequirementKind
    weight: float = 1.0
    source_quote: str | None = None


class EligibilityRule(OppModel):
    """지원 자격 조건. 판정은 `backend/eligibility.py` 하나로만 한다 (D-11, db-schema §3.2)."""

    rule_id: str
    type: RuleType
    value: Any = None
    source_quote: str | None = None


class RegionalCondition(OppModel):
    """공고문에서 읽은 지역 조건 하나. 지역이 여럿이면 지역마다 하나씩 둔다.

    sido는 시·도 코드, sigungu는 시·군·구 이름("김해시", "기장군")이다. NON_CAPITAL과 UNKNOWN은 지역이 없다.
    """

    kind: RegionalBenefitKind
    sido: str | None = None
    sigungu: str | None = None
    label: str | None = None  # 원문 표기 ("비수도권 지역인재", "경상남도 김해시")


class RegionalTalent(OppModel):
    """공고 쪽 지역 조건. status는 공고에 지역 조건이 있는지(LIKELY), 부산 이전기관인데 공고문에서 못 찾았는지
    (CHECK_NEEDED), 없는지(NOT_APPLICABLE)다. 사용자에게 맞는지는 `core.facts.regional_talent_view`가 본다."""

    status: RegionalTalentStatus
    basis: str | None = None
    conditions: list[RegionalCondition] = Field(default_factory=list)


class PostingSnapshot(OppModel):
    # 팀 필드
    job_posting_id: str
    snapshot_id: str
    title: str
    organization: str
    company_id: str | None = None
    job_description: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    eligibility_rules: list[EligibilityRule] = Field(default_factory=list)
    closes_at: str = ROLLING_CLOSES_AT
    official_url: str | None = None
    source_type: SourceType = SourceType.OFFICIAL
    checked_at: str
    # B 필드
    source: PostingSource
    company: Company
    org_type: OrgType = OrgType.PRIVATE
    work_region: WorkRegion = Field(default_factory=WorkRegion)
    job: Job
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    career_type: CareerType = CareerType.UNKNOWN
    education_min: EducationLevel | None = None
    salary: Salary = Field(default_factory=Salary)
    rolling: bool = False
    remote_work: RemoteWork = RemoteWork.UNKNOWN
    selection_steps: list[str] = Field(default_factory=list)
    documents: list[str] = Field(default_factory=list)
    badges: list[Badge] = Field(default_factory=list)
    regional_talent: RegionalTalent | None = None
    extract_status: ExtractStatus = ExtractStatus.PENDING
    extracted_by: dict[str, ExtractedBy] = Field(default_factory=dict)  # 필드 이름 → 값을 만든 주체
    content_hash: str


class PostingLatest(OppModel):
    """목록용. 피드와 대안은 이 아이템만 읽는다."""

    job_posting_id: str
    snapshot_id: str
    title: str
    organization: str
    is_expired: bool = False
    is_sample: bool = False
    closes_at: str = ROLLING_CLOSES_AT
    checked_at: str
    # 목록용 B 값
    is_busan: bool = False
    is_capital_area: bool = False
    is_overseas: bool = False
    work_region: WorkRegion = Field(default_factory=WorkRegion)
    job: Job
    salary: Salary = Field(default_factory=Salary)
    remote_work: RemoteWork = RemoteWork.UNKNOWN
    badges: list[Badge] = Field(default_factory=list)
    org_type: OrgType = OrgType.PRIVATE
    company_id: str | None = None
    rolling: bool = False
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    career_type: CareerType = CareerType.UNKNOWN
    regional_talent: RegionalTalent | None = None
    eligibility_rules: list[EligibilityRule] = Field(default_factory=list)
    required_names: list[str] = Field(default_factory=list)   # REQUIRED_SKILL 이름
    preferred_names: list[str] = Field(default_factory=list)  # PREFERRED_SKILL 이름
    extract_status: ExtractStatus = ExtractStatus.PENDING


class AltCandidate(OppModel):
    job_posting_id: str
    similarity: float


class AltCandidates(OppModel):
    """수도권 공고마다 미리 계산한 부산 후보 (최대 10)."""

    job_posting_id: str
    candidates: list[AltCandidate] = Field(default_factory=list)
    computed_at: str


class CompanyRecord(OppModel):
    """청끌기업·강소기업·이전기관 시드 (COMPANY#). source·asOf가 없으면 로더가 거부한다."""

    company_id: str
    name: str
    biz_no: str | None = None
    sido: str | None = None
    industry: str | None = None
    size: str | None = None
    highlights: list[Badge] = Field(default_factory=list)
    regional_talent: bool = False  # 이전기관이면 지역인재 채용 대상
    district: str | None = None      # 소재 구·군 (원문)
    main_product: str | None = None  # 주력 제품 (원문)
    source: str
    as_of: str


class OrgPayYear(OppModel):
    """한 해의 일반정규직 1인당 평균 보수액. 금액은 만 원/년이다 (공시 단위 천 원을 10으로 나눠 반올림)."""

    year: int
    average: int
    budget: bool = False  # True면 그해 예산(아직 결산 전)


class OrgPay(OppModel):
    """공공기관 직원 평균보수 (`ORGPAY` / `ORG#{orgId}`). 알리오 경영공시 「직원 평균보수」의 일반정규직 표와,
    클린아이의 지방출자·출연기관 직원평균임금(행정안전부 파일, `seeds/klid_org_pay.json`)이다.

    직원 전체의 평균이라 신입 초봉이 아니다. 화면·대화에서는 "기관 평균"으로만 말한다 (DECISIONS B-D11).
    orgId는 알리오 기관 코드(C0072, 채용공시의 pblntInstCd와 같다)나 `klid-` 해시다. 공고와는 기관 이름으로 잇는다.
    """

    org_id: str
    name: str
    org_type: str | None = None   # 공기업(시장형), 준정부기관(위탁집행형), 기타공공기관 …
    ministry: str | None = None   # 주무부처. 지방출자·출연기관은 설립 지자체
    years: list[OrgPayYear] = Field(default_factory=list)  # 오래된 해부터
    latest_year: int              # 가장 최근 결산 연도
    latest_average: int           # 그해 1인당 평균 보수액 (만 원/년)
    year_note: str = "결산"  # 연도 뒤에 붙이는 말 ("2025년 결산"). 출처가 밝히지 않으면 빈 글 (연도만 쓴다)
    tenure_months: int | None = None  # 그해 평균근속연수 (개월)
    source: str
    as_of: str                    # 공시 기준일 (YYYY-MM-DD)
    source_url: str


class RegionalIndexEntry(OppModel):
    """지역 조건이 있는 공고 색인 한 줄 (`INDEX#REGIONAL` / `POSTING#{id}`). 피드의 지역 혜택 거르기가 벡터 상위 후보
    밖의 공고까지 찾으려고 읽는다. 수집·보강이 LATEST를 쓸 때 함께 쓰고 지운다."""

    job_posting_id: str
    closes_at: str


class VectorMeta(OppModel):
    """S3 Vectors 메타데이터. title만 필터 불가 값이다."""

    is_busan: bool
    sido: str
    job_major: str
    active: bool
    deadline: int  # YYYYMMDD 숫자
    title: str


class PostingName(OppModel):
    """공고 이름 색인 한 줄 (B-D08). 진행 중 공고만 둔다. 만드는 곳은 `core/name_index.name_row` 하나다.

    `team07-catalog`의 `POSTNAMES` / `POSTING#{jobPostingId}`. LATEST를 쓸 때 같이 쓰고, 마감 처리하면 지운다.
    검색어·회사 이름 검색과, 로그인 없이 보는 공고 목록의 분류(B-D10)에 쓴다.
    """

    job_posting_id: str
    organization: str
    title: str
    job_name: str | None = None
    closes_at: str
    # 분류 (B-D10). 이 칸이 생기기 전에 쓴 줄은 기본값이라 다시 채워야 한다
    org_type: OrgType = OrgType.PRIVATE
    sido: str | None = None  # 해외·근무지 미상이면 없음
    is_overseas: bool = False
    career_type: CareerType = CareerType.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN


def latest_from_snapshot(snap: PostingSnapshot, *, busan_sido: str, capital_sido: list[str],
                         is_expired: bool = False) -> PostingLatest:
    """스냅샷에서 목록용 아이템을 만든다. 수집·보강이 같은 규칙으로 쓰게 한 곳에 둔다."""
    sido = None if snap.work_region.unknown or snap.work_region.overseas else snap.work_region.sido
    return PostingLatest(
        job_posting_id=snap.job_posting_id,
        snapshot_id=snap.snapshot_id,
        title=snap.title,
        organization=snap.organization,
        is_expired=is_expired,
        is_sample=snap.source_type == SourceType.DEMO,
        closes_at=snap.closes_at,
        checked_at=snap.checked_at,
        is_busan=sido == busan_sido,
        is_capital_area=sido in capital_sido,
        is_overseas=snap.work_region.overseas,
        work_region=snap.work_region,
        job=snap.job,
        salary=snap.salary,
        remote_work=snap.remote_work,
        badges=snap.badges,
        org_type=snap.org_type,
        company_id=snap.company_id,
        rolling=snap.rolling,
        employment_type=snap.employment_type,
        career_type=snap.career_type,
        regional_talent=snap.regional_talent,
        eligibility_rules=snap.eligibility_rules,
        required_names=[r.name for r in snap.requirements if r.kind == RequirementKind.REQUIRED_SKILL],
        preferred_names=[r.name for r in snap.requirements if r.kind == RequirementKind.PREFERRED_SKILL],
        extract_status=snap.extract_status,
    )
