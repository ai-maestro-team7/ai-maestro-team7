"""Common_Profile (R7, D-08·D-33, docs/db-schema.md §2.1 PROFILE#BASIC, docs/api.md §6.5 기본 프로필).

모든 필드가 선택이고 null은 PUT에서 "그 필드 삭제"를 뜻한다.
값 규칙은 backend/me_api.py PROFILE_FIELDS와 같다. 실명·연락처·주민번호 필드는 없다 (product.md 원칙 7).
"""
from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import AfterValidator, Field, StrictBool, StrictInt

from .base import Code20, ContractModel, SidoCode, SigunguCode, YearMonth, non_blank
from .validation import CrossFieldError

Priority = Literal["SALARY", "GROWTH", "STABILITY", "WORK_LIFE", "HOUSING", "LOCATION"]


def _region(value: str) -> str:
    if value != "ALL" and not (len(value) == 2 and value.isdigit()):
        raise CrossFieldError([("", "pattern")])
    return value


class DesiredJob(ContractModel):
    name: Annotated[str, non_blank(50)]
    work24_code: Optional[Code20] = None  # 고용24 직종 코드 (docs/api.md §6.2)
    ncs_code: Optional[Code20] = None


class CommonProfile(ContractModel):
    birth_year: Optional[Annotated[StrictInt, Field(ge=1950, le=2015)]] = None
    residence_sido: Optional[SidoCode] = None
    residence_sigungu: Optional[SigunguCode] = None
    residence_since: Optional[YearMonth] = None
    # 최종 학교 소재지 시·도. 지역인재 판정에 쓴다. 대학원까지 마쳤으면 학부 대학, 고졸이면 고등학교 소재지
    university_region: Optional[SidoCode] = None
    school_name: Optional[Annotated[str, non_blank(50)]] = None  # 대학 이름 (전문대 이상만, 고졸은 비운다)
    graduation_status: Optional[Literal["ENROLLED", "GRADUATING", "GRADUATED"]] = None
    education_level: Optional[Literal["HIGH_SCHOOL", "ASSOCIATE", "BACHELOR", "MASTER", "DOCTOR"]] = None
    major: Optional[Annotated[str, non_blank(50)]] = None
    career_years: Optional[Annotated[StrictInt, Field(ge=0, le=50)]] = None
    employment_status: Optional[Literal["UNEMPLOYED", "EMPLOYED", "PART_TIME", "STUDENT"]] = None
    monthly_income: Optional[Annotated[StrictInt, Field(ge=0, le=100_000_000)]] = None  # 원 단위, 단위 필드 없는 예외
    household_income_level: Optional[Literal["under_100", "under_150", "over_150", "unknown"]] = None
    desired_jobs: Optional[Annotated[list[DesiredJob], Field(max_length=3)]] = None
    desired_region: Optional[Annotated[str, AfterValidator(_region)]] = None
    priorities: Optional[Annotated[list[Priority], Field(max_length=3)]] = None
    talent_pool_consent: Optional[StrictBool] = None
    # 가진 자격증 이름 (사용자 입력, 최대 10개). 공고의 자격 요건·우대 조건과 맞춰 본다
    certificates: Optional[Annotated[list[Annotated[str, non_blank(50)]], Field(max_length=10)]] = None
