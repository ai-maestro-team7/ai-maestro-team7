"""B에서 쓰는 열거형. 값은 `docs/db-schema.md` v1.3과 `docs/개발계획서2.md` 기준이다."""

from enum import StrEnum


class PostingSource(StrEnum):
    WORK24 = "WORK24"            # 고용24 채용정보 (wk24-)
    ALIO = "ALIO"                # 잡알리오 채용공시 (alio-)
    EXTERNAL = "EXTERNAL"        # 사용자가 붙여넣은 공고 (ext-, P1)
    PARTNER = "PARTNER"          # 기업 직접 등록 (ptn-, 2차 예약)
    SCHOOL_PROGRAM = "SCHOOL_PROGRAM"  # 학교 프로그램 (sch-, 2차 예약)
    DEMO = "DEMO"                # 직접 정리한 데모 공고


class SourceType(StrEnum):
    OFFICIAL = "OFFICIAL"
    DEMO = "DEMO"


class OrgType(StrEnum):
    PRIVATE = "PRIVATE"
    PUBLIC_INSTITUTION = "PUBLIC_INSTITUTION"
    LOCAL_PUBLIC = "LOCAL_PUBLIC"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    CONTRACT = "CONTRACT"
    PART_TIME = "PART_TIME"
    INTERN = "INTERN"
    UNKNOWN = "UNKNOWN"


class CareerType(StrEnum):
    NEW = "NEW"
    EXPERIENCED = "EXPERIENCED"
    ANY = "ANY"
    UNKNOWN = "UNKNOWN"


class EducationLevel(StrEnum):
    NONE = "NONE"
    HIGH_SCHOOL = "HIGH_SCHOOL"
    ASSOCIATE = "ASSOCIATE"
    BACHELOR = "BACHELOR"
    MASTER = "MASTER"
    DOCTOR = "DOCTOR"


class RemoteWork(StrEnum):
    FULL = "FULL"
    HYBRID = "HYBRID"
    NONE = "NONE"
    UNKNOWN = "UNKNOWN"


class MoneyUnit(StrEnum):
    MANWON_YEAR = "MANWON_YEAR"
    MANWON_MONTH = "MANWON_MONTH"
    MANWON = "MANWON"
    WON = "WON"


class ExtractStatus(StrEnum):
    PENDING = "PENDING"
    DONE = "DONE"
    FAILED = "FAILED"


class ExtractedBy(StrEnum):
    API = "API"
    LLM = "LLM"
    MANUAL = "MANUAL"


class RequirementKind(StrEnum):
    REQUIRED_SKILL = "REQUIRED_SKILL"
    PREFERRED_SKILL = "PREFERRED_SKILL"


class RuleType(StrEnum):
    EDUCATION = "EDUCATION"
    CAREER = "CAREER"
    CERTIFICATE = "CERTIFICATE"
    MAJOR = "MAJOR"
    OTHER = "OTHER"


class ConditionResult(StrEnum):
    MET = "MET"
    NOT_MET = "NOT_MET"
    UNKNOWN = "UNKNOWN"


class EligibilityStatus(StrEnum):
    """공고 지원 자격 전체 결과 (D-11, `backend/eligibility.py`)."""

    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class RegionalTalentStatus(StrEnum):
    LIKELY = "LIKELY"
    CHECK_NEEDED = "CHECK_NEEDED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BadgeType(StrEnum):
    CHEONGKKEUL = "CHEONGKKEUL"                    # 청끌기업
    GANGSO = "GANGSO"                              # 청년일자리강소기업
    RELOCATED_INSTITUTION = "RELOCATED_INSTITUTION"  # 부산 이전 공공기관
    REMOTE_WORK = "REMOTE_WORK"                    # 원격 근무 가능


class CheonggeulType(StrEnum):
    SALARY = "SALARY"        # 급여
    WELFARE = "WELFARE"      # 복지
    WORK_LIFE = "WORK_LIFE"  # 워라밸
    FUTURE = "FUTURE"        # 미래


class Sort(StrEnum):
    BUSAN_FIRST = "BUSAN_FIRST"
    MATCH = "MATCH"
    DEADLINE = "DEADLINE"
    RECENT = "RECENT"


class LeaveReason(StrEnum):
    SALARY = "SALARY"
    NO_JOB_IN_BUSAN = "NO_JOB_IN_BUSAN"
    GROWTH = "GROWTH"
    WORK_LIFE = "WORK_LIFE"
    HOUSING = "HOUSING"
    WANT_SEOUL_LIFE = "WANT_SEOUL_LIFE"
    SKIP = "SKIP"


class MatchLevel(StrEnum):
    GOOD = "GOOD"  # 잘 맞아요
    FAIR = "FAIR"  # 맞는 편이에요
    LOW = "LOW"    # 조금 맞아요


class SavedKind(StrEnum):
    INTEREST = "INTEREST"
    TARGET = "TARGET"


class WorkspaceStatus(StrEnum):
    INTEREST = "INTEREST"
    PLANNED = "PLANNED"
    PREPARING = "PREPARING"
    APPLIED = "APPLIED"
    RESULT = "RESULT"
    CLOSED = "CLOSED"


class EmploymentStatus(StrEnum):
    UNEMPLOYED = "UNEMPLOYED"
    EMPLOYED = "EMPLOYED"
    STUDENT = "STUDENT"


class PolicyKind(StrEnum):
    POLICY = "POLICY"
    EVENT = "EVENT"


class PolicySource(StrEnum):
    YOUTHCENTER = "YOUTHCENTER"  # 온통청년 (ythc-)
    BUSAN_SEED = "BUSAN_SEED"    # 직접 정리한 부산 시드 (seed-)
    BUSAN_CITY = "BUSAN_CITY"    # 부산광역시 청년지원프로그램 API


class PolicyStage(StrEnum):
    PREPARE = "PREPARE"    # 취업 준비
    EMPLOYED = "EMPLOYED"  # 취업 후
    SETTLE = "SETTLE"      # 정착


class PolicyBucket(StrEnum):
    OPEN_NOW = "OPEN_NOW"
    NEXT_CYCLE = "NEXT_CYCLE"
    AFTER_EMPLOYMENT = "AFTER_EMPLOYMENT"
    SETTLEMENT = "SETTLEMENT"
    CLOSED = "CLOSED"


class PolicyEligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CHECK_NEEDED = "CHECK_NEEDED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    AFTER_EMPLOYMENT = "AFTER_EMPLOYMENT"  # 취업하면 대상


class RegionScope(StrEnum):
    NATIONAL = "NATIONAL"
    SIDO = "SIDO"
    SIGUNGU = "SIGUNGU"


class Selection(StrEnum):
    AUTOMATIC = "AUTOMATIC"    # 자격만 맞으면 받음
    FIRST_COME = "FIRST_COME"  # 선착순
    LOTTERY = "LOTTERY"        # 추첨
    REVIEW = "REVIEW"          # 심사


class PeriodType(StrEnum):
    FIXED = "FIXED"      # 모집 기간이 정해져 있음
    ALWAYS = "ALWAYS"    # 상시
    MONTHLY = "MONTHLY"  # 매월
    TBD = "TBD"          # 다음 일정 미정


class NotificationType(StrEnum):
    POLICY_OPEN = "POLICY_OPEN"
    POLICY_CLOSING = "POLICY_CLOSING"
    TARGET_DEADLINE = "TARGET_DEADLINE"
    NEW_BUSAN_SIMILAR = "NEW_BUSAN_SIMILAR"  # P1
    WEEKLY_REPORT = "WEEKLY_REPORT"          # P1


class NotificationChannel(StrEnum):
    INBOX = "INBOX"
    EMAIL = "EMAIL"


class TrackEvent(StrEnum):
    # 프론트가 POST /track으로 보내는 것
    ALT_CLICKED = "ALT_CLICKED"
    COMPARE_OPENED = "COMPARE_OPENED"
    COST_TOGGLE_ON = "COST_TOGGLE_ON"
    BUSAN_FIRST_OFF = "BUSAN_FIRST_OFF"
    POLICY_LINK_CLICKED = "POLICY_LINK_CLICKED"
    # 서버가 남기는 것
    ALT_SHOWN = "ALT_SHOWN"
    SAVED = "SAVED"
    NO_ALTERNATIVE = "NO_ALTERNATIVE"


class CompareKey(StrEnum):
    SALARY = "SALARY"
    HOUSING = "HOUSING"
    COMMUTE = "COMMUTE"
    REGIONAL_POLICY = "REGIONAL_POLICY"
    REGIONAL_TALENT = "REGIONAL_TALENT"
    VERIFIED = "VERIFIED"
