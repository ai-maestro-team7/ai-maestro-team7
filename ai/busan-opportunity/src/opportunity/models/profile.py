"""프로필과 B 설정. 공통 프로필은 읽기만 한다 (`PROFILE#BASIC`, db-schema §2.1)."""

from pydantic import Field

from .base import OppModel
from .enums import EducationLevel, EmploymentStatus, LeaveReason, Sort


class DesiredJob(OppModel):
    work24_code: str | None = None
    ncs_code: str | None = None
    name: str


class BasicProfile(OppModel):
    birth_year: int | None = None
    residence_sido: str | None = None
    residence_sigungu: str | None = None
    residence_since: str | None = None
    university_region: str | None = None  # 최종(예정) 학교 소재지 시·도
    graduation_status: str | None = None  # ENROLLED, GRADUATING, GRADUATED …
    employment_status: EmploymentStatus | None = None
    monthly_income: int | None = None
    household_income_level: int | None = None
    desired_jobs: list[DesiredJob] = Field(default_factory=list)
    desired_region: str | None = None
    education_level: EducationLevel | None = None
    major: str | None = None
    priorities: list[str] = Field(default_factory=list)
    career_years: int | None = None
    talent_pool_consent: bool = False  # 2차 예약. 지금은 쓰지 않는다
    is_demo: bool = False
    # A의 역량 프로필에서 오는 값 (P1). 없으면 온보딩 정보만으로 추천한다
    skills: list[str] = Field(default_factory=list)
    certificates: list[str] = Field(default_factory=list)
    confirmed_missing_certificates: list[str] = Field(default_factory=list)


class NotificationPrefs(OppModel):
    email: bool = False
    weekly: bool = False


class OppPrefs(OppModel):
    """`OPP#PREFS`. 없으면 기본값을 쓴다."""

    sort: Sort = Sort.BUSAN_FIRST
    leave_reason: LeaveReason | None = None
    leave_reason_asked_at: str | None = None
    notifications: NotificationPrefs = Field(default_factory=NotificationPrefs)
    receiving_policies: list[str] = Field(default_factory=list)  # 받는 중이라고 표시한 정책 이름·ID
    demo_as_of: str | None = None
