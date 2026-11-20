"""데모·테스트용 데이터. 회사와 기관은 모두 가상이고 공고는 `sourceType=DEMO`(isSample=true)다.

- 사용자 `demo1`~`demo3`은 개발계획서2 §7.1의 페르소나 ①②③이다 (`infra/seed_demo.py`와 같은 프로필).
- 직종 코드는 데모용 값이다. 고용24 실제 코드는 첫 수집 뒤 매핑표로 바꾼다.
- 부산 시드 정책의 값은 개발계획서2 §3.4의 조사값이고 원문 확인 전이다. 여기서만 verified=true(DEMO)로 둔다.
- `[데모]`가 붙은 온통청년 정책과 지역 통계는 규칙을 시험하려고 만든 가짜 값이다.

기준 시각은 DEMO_AS_OF (2026-11-21 10:00 KST)다.
"""

import hashlib

from ..config import OpportunityConfig, load_config
from ..core.texts import posting_text
from ..deps import Deps
from ..ingest.pipeline import sync_regional_index
from ..models.enums import (
    BadgeType,
    CareerType,
    CheonggeulType,
    EducationLevel,
    EmploymentStatus,
    EmploymentType,
    ExtractStatus,
    OrgType,
    PeriodType,
    PolicySource,
    PolicyStage,
    PostingSource,
    RegionalTalentStatus,
    RegionScope,
    RemoteWork,
    RequirementKind,
    RuleType,
    Selection,
    SourceType,
)
from ..models.policy import (
    IncomeRule,
    Policy,
    PolicyApplication,
    PolicyBenefit,
    PolicyCycle,
    PolicyEligibility,
    PolicyRegion,
)
from ..models.posting import (
    AltCandidate,
    AltCandidates,
    Badge,
    Company,
    CompanyRecord,
    EligibilityRule,
    Job,
    PostingSnapshot,
    RegionalTalent,
    Requirement,
    Salary,
    VectorMeta,
    WorkRegion,
    latest_from_snapshot,
)
from ..models.profile import BasicProfile, DesiredJob
from ..models.region import CommuteStat, RegionStats, RentStat
from ..store.memory import (
    KeywordEmbedder,
    MemoryCatalog,
    MemoryEvents,
    MemoryMailer,
    MemoryScheduler,
    MemoryUsers,
    MemoryVectors,
    MemoryWorkspaces,
)

DEMO_AS_OF = "2026-11-21T10:00:00+09:00"
DATA_AS_OF = "2026-11-21T04:52:00+09:00"
CHECKED_AT = "2026-11-21T04:40:00+09:00"
SNAP_DAY = "20261121"

# 데모용 직종 코드: (세분류, 중분류, 대분류, 이름)
JOB_DATA = ("D0101", "D01", "D", "데이터 분석가")
JOB_DATA_ENG = ("D0102", "D01", "D", "데이터 엔지니어")
JOB_BACKEND = ("D0201", "D02", "D", "백엔드 개발자")
JOB_ACCOUNT = ("A0201", "A02", "A", "사무·회계")
JOB_FINANCE = ("F0101", "F01", "F", "공공기관 금융·행정")
JOB_ADMIN = ("F0102", "F01", "F", "공공기관 행정")
JOB_GAME = ("G0301", "G03", "G", "게임 클라이언트 개발자")

CHEONGGEUL_SRC = {"source": "부산광역시 (데모)", "as_of": "2026-06-30"}
GANGSO_SRC = {"source": "고용노동부 (데모)", "as_of": "2026-06-30"}
RELOCATED_SRC = {"source": "국토교통부 혁신도시 (데모)", "as_of": "2026-06-30"}


def _job(spec, ncs=None) -> Job:
    code, middle, major, name = spec
    return Job(code=code, middle=middle, major=major, name=name, ncs_codes=ncs or [])


def _reqs(required=(), preferred=()) -> list[Requirement]:
    rows = [Requirement(requirement_id=f"req-{i + 1}", name=name, kind=RequirementKind.REQUIRED_SKILL,
                        source_quote=f"필수: {name}") for i, name in enumerate(required)]
    rows += [Requirement(requirement_id=f"pref-{i + 1}", name=name, kind=RequirementKind.PREFERRED_SKILL,
                         source_quote=f"우대: {name}") for i, name in enumerate(preferred)]
    return rows


def _rules(education=None, career=None, certificates=(), majors=None) -> list[EligibilityRule]:
    rows = []
    if education is not None:
        rows.append(EligibilityRule(rule_id="rule-edu", type=RuleType.EDUCATION, value=education,
                                    source_quote="학력 조건"))
    if career is not None:
        rows.append(EligibilityRule(rule_id="rule-career", type=RuleType.CAREER, value=career,
                                    source_quote="경력 조건"))
    for i, name in enumerate(certificates):
        rows.append(EligibilityRule(rule_id=f"rule-cert-{i + 1}", type=RuleType.CERTIFICATE, value=name,
                                    source_quote=f"필수 자격증: {name}"))
    if majors:
        rows.append(EligibilityRule(rule_id="rule-major", type=RuleType.MAJOR, value=majors,
                                    source_quote="전공 조건"))
    return rows


def _posting(pid, title, org, region, job, *, source=PostingSource.WORK24, org_type=OrgType.PRIVATE,
             salary=None, closes="9999-12-31", description="", required=(), preferred=(), rules=None,
             badges=(), regional_talent=None, remote=RemoteWork.NONE, career=CareerType.NEW,
             company_id=None, hq_sido=None) -> PostingSnapshot:
    sido, sigungu, label = region
    return PostingSnapshot(
        job_posting_id=pid, snapshot_id=f"{SNAP_DAY}-{hashlib.sha256(pid.encode()).hexdigest()[:8]}", title=title, organization=org,
        company_id=company_id, job_description=description, requirements=_reqs(required, preferred),
        eligibility_rules=rules if rules is not None else _rules(education="NONE", career={"type": "NEW"}),
        closes_at=closes, official_url=f"https://example.invalid/postings/{pid}", source_type=SourceType.DEMO,
        checked_at=CHECKED_AT, source=source, company=Company(name=org, hq_sido=hq_sido or sido), org_type=org_type,
        work_region=WorkRegion(sido=sido, sigungu=sigungu, label=label, unknown=sido is None),
        job=_job(job), employment_type=EmploymentType.FULL_TIME, career_type=career,
        salary=Salary(disclosed=True, min=salary[0], max=salary[1]) if salary else Salary(disclosed=False),
        rolling=closes == "9999-12-31", remote_work=remote, badges=list(badges), regional_talent=regional_talent,
        extract_status=ExtractStatus.DONE, content_hash=f"demo-{pid}",
    )


HAEUNDAE = ("26", "26350", "부산 해운대구")
NAMGU = ("26", "26290", "부산 남구")
SAHA = ("26", "26380", "부산 사하구")
BUSANJIN = ("26", "26230", "부산 부산진구")
YEONGDO = ("26", "26200", "부산 영도구")
GANGNAM = ("11", "11680", "서울 강남구")
MAPO = ("11", "11440", "서울 마포구")
JUNG = ("11", "11140", "서울 중구")
YEONGDEUNGPO = ("11", "11560", "서울 영등포구")
SEONGNAM = ("41", "41135", "경기 성남시 분당구")
UNKNOWN_REGION = (None, None, "근무지 확인 필요")

BADGE_CG_SALARY = Badge(type=BadgeType.CHEONGKKEUL, label="청끌기업 · 급여", cheonggeul_type=CheonggeulType.SALARY,
                        **CHEONGGEUL_SRC)
BADGE_CG_WORKLIFE = Badge(type=BadgeType.CHEONGKKEUL, label="청끌기업 · 워라밸",
                          cheonggeul_type=CheonggeulType.WORK_LIFE, **CHEONGGEUL_SRC)
BADGE_GANGSO = Badge(type=BadgeType.GANGSO, label="청년일자리강소기업", **GANGSO_SRC)
BADGE_RELOCATED = Badge(type=BadgeType.RELOCATED_INSTITUTION, label="부산 이전 공공기관", **RELOCATED_SRC)
BADGE_REMOTE = Badge(type=BadgeType.REMOTE_WORK, label="원격 근무 가능", source="공고 원문", as_of="2026-11-21")
BADGE_NO_SOURCE = Badge(type=BadgeType.CHEONGKKEUL, label="청끌기업")  # 출처·기준일 없음 → 응답에서 빠져야 한다 (T-08)

# 자주 쓰는 공고 ID
BUSAN_DATA = "wk24-DEMO0001"        # 부산 데이터 분석, 청끌기업(급여)
BUSAN_DATA_PUBLIC = "alio-DEMO0001"  # 부산 이전기관 데이터 직무, 지역인재 LIKELY, 급여 미기재
SEOUL_DATA = "wk24-DEMO0002"        # 서울 데이터 분석, 급여가 부산보다 높다
SEOUL_DATA_HYBRID = "wk24-DEMO0003"  # 서울 데이터 분석, 원격 근무
GYEONGGI_DATA_ENG = "wk24-DEMO0004"  # 경기 데이터 엔지니어, 경력 3년 (ALTS 없음)
BUSAN_ACCOUNT = "wk24-DEMO0005"     # 부산 사무·회계, 청끌기업(워라밸)
BUSAN_ACCOUNT_GANGSO = "wk24-DEMO0006"  # 부산 회계, 강소기업, 상시 채용, 급여 미기재
SEOUL_ACCOUNT = "wk24-DEMO0007"     # 서울 재무회계 (ALTS 없음)
BUSAN_FINANCE_PUBLIC = "alio-DEMO0002"  # 부산 이전기관 금융·행정, 지역인재 LIKELY
BUSAN_ADMIN_PUBLIC = "alio-DEMO0003"    # 부산 이전기관 행정, 지역인재 CHECK_NEEDED
BUSAN_DATA_EXPIRED = "wk24-DEMO0008"    # 마감 (isExpired=true)
BUSAN_DATA_JUST_CLOSED = "wk24-DEMO0009"  # 어제 마감, isExpired는 아직 false
DATA_UNKNOWN_REGION = "wk24-DEMO0010"   # 근무지 미상. 부산으로 세지 않는다
SEOUL_GAME = "wk24-DEMO0011"        # 서울 게임 클라이언트. 부산 대안이 없다 (T-15)
BUSAN_BACKEND = "wk24-DEMO0012"     # 부산 백엔드 개발
SEOUL_FINANCE_PUBLIC = "alio-DEMO0004"  # 서울 공공기관 금융
BUSAN_BADGE_NO_SOURCE = "wk24-DEMO0013"  # 출처 없는 배지가 붙은 부산 사무 공고 (T-08)


def build_snapshots() -> list[PostingSnapshot]:
    talent_likely = RegionalTalent(status=RegionalTalentStatus.LIKELY, basis="공고문에 지역인재 채용목표제 적용 명시")
    talent_check = RegionalTalent(status=RegionalTalentStatus.CHECK_NEEDED, basis="이전 공공기관이나 공고문에서 언급을 찾지 못함")
    data_desc = "데이터 분석과 통계 모델링으로 서비스 지표를 분석하고 SQL로 데이터를 다룬다"
    return [
        _posting(BUSAN_DATA, "데이터 분석 신입", "(주)가상데이터", HAEUNDAE, JOB_DATA, salary=(3400, 3800),
                 closes="2026-12-05", description=data_desc, required=("SQL", "Python"), preferred=("ADsP",),
                 rules=_rules(education="BACHELOR", career={"type": "NEW"}), badges=[BADGE_CG_SALARY],
                 company_id="biz-DEMO000001"),
        _posting(BUSAN_DATA_PUBLIC, "2026년 신입직원 채용 (데이터)", "가상금융공사", NAMGU, JOB_DATA,
                 source=PostingSource.ALIO, org_type=OrgType.PUBLIC_INSTITUTION, closes="2026-11-30",
                 description="데이터 분석과 통계로 기금 운용 데이터를 분석한다", required=("통계 분석",),
                 preferred=("SQL",), badges=[BADGE_RELOCATED], regional_talent=talent_likely,
                 company_id="biz-DEMO000101"),
        _posting(SEOUL_DATA, "Data Analyst", "(주)가상테크", GANGNAM, JOB_DATA, salary=(4000, 4400),
                 closes="2026-11-30", description=data_desc, required=("SQL", "Python"), preferred=("Tableau",),
                 rules=_rules(education="BACHELOR", career={"type": "NEW"})),
        _posting(SEOUL_DATA_HYBRID, "데이터 분석가 (하이브리드 근무)", "(주)가상커머스", MAPO, JOB_DATA,
                 salary=(3800, 4200), closes="2026-12-10", description=data_desc, required=("SQL",),
                 remote=RemoteWork.HYBRID, badges=[BADGE_REMOTE]),
        _posting(GYEONGGI_DATA_ENG, "데이터 엔지니어", "(주)가상클라우드", SEONGNAM, JOB_DATA_ENG,
                 salary=(4200, 5000), closes="2026-12-15", description="데이터 파이프라인을 개발하고 운영하는 데이터 엔지니어",
                 required=("Python", "Spark"), rules=_rules(education="BACHELOR",
                                                            career={"type": "EXPERIENCED", "minYears": 3}),
                 career=CareerType.EXPERIENCED),
        _posting(BUSAN_ACCOUNT, "경영지원 사무·회계", "(주)가상상사", SAHA, JOB_ACCOUNT, salary=(2800, 3000),
                 closes="2026-12-12", description="회계 전표 처리와 경영 지원 사무", required=("전산회계",),
                 preferred=("엑셀",), rules=_rules(education="ASSOCIATE", career={"type": "ANY"}),
                 badges=[BADGE_CG_WORKLIFE], company_id="biz-DEMO000002"),
        _posting(BUSAN_ACCOUNT_GANGSO, "회계 사무원", "(주)가상정밀", BUSANJIN, JOB_ACCOUNT,
                 description="회계 장부 관리와 사무 지원", required=("전산회계",), badges=[BADGE_GANGSO],
                 company_id="biz-DEMO000003"),
        _posting(SEOUL_ACCOUNT, "재무회계 담당", "(주)가상유통", JUNG, JOB_ACCOUNT, salary=(3200, 3600),
                 closes="2026-12-01", description="재무회계 결산과 세무 신고", required=("전산회계", "전산세무")),
        _posting(BUSAN_FINANCE_PUBLIC, "일반행정·금융 신입 채용", "가상주택금융공사", NAMGU, JOB_FINANCE,
                 source=PostingSource.ALIO, org_type=OrgType.PUBLIC_INSTITUTION, salary=(3600, 3600),
                 closes="2026-12-08", description="주택금융 상품 운영과 공공 행정", badges=[BADGE_RELOCATED],
                 regional_talent=talent_likely, company_id="biz-DEMO000102"),
        _posting(BUSAN_ADMIN_PUBLIC, "행정직 채용", "가상해양공단", YEONGDO, JOB_ADMIN, source=PostingSource.ALIO,
                 org_type=OrgType.PUBLIC_INSTITUTION, closes="2026-12-20", description="공단 행정 업무",
                 badges=[BADGE_RELOCATED], regional_talent=talent_check, company_id="biz-DEMO000103"),
        _posting(BUSAN_DATA_EXPIRED, "데이터 분석 (마감)", "(주)가상지난", HAEUNDAE, JOB_DATA, salary=(3000, 3200),
                 closes="2026-11-10", description=data_desc, required=("SQL",)),
        _posting(BUSAN_DATA_JUST_CLOSED, "데이터 분석 (어제 마감)", "(주)가상어제", HAEUNDAE, JOB_DATA,
                 salary=(3000, 3200), closes="2026-11-20", description=data_desc, required=("SQL",)),
        _posting(DATA_UNKNOWN_REGION, "데이터 분석 (근무지 미기재)", "(주)가상미상", UNKNOWN_REGION, JOB_DATA,
                 closes="2026-12-03", description=data_desc, required=("SQL",), hq_sido="26"),
        _posting(SEOUL_GAME, "게임 클라이언트 개발자", "(주)가상게임즈", GANGNAM, JOB_GAME, salary=(4500, 5500),
                 closes="2026-12-09", description="게임 클라이언트와 그래픽스 엔진 개발", required=("C++",)),
        _posting(BUSAN_BACKEND, "백엔드 개발자", "(주)가상소프트", HAEUNDAE, JOB_BACKEND, salary=(3500, 4000),
                 closes="2026-12-11", description="서버 백엔드 개발", required=("Python",)),
        _posting(SEOUL_FINANCE_PUBLIC, "금융·행정 신입 채용", "가상서울금융공단", YEONGDEUNGPO, JOB_FINANCE,
                 source=PostingSource.ALIO, org_type=OrgType.PUBLIC_INSTITUTION, salary=(3800, 3800),
                 closes="2026-12-07", description="금융 상품 운영과 공공 행정"),
        _posting(BUSAN_BADGE_NO_SOURCE, "총무 사무", "(주)가상무역", BUSANJIN, JOB_ACCOUNT, salary=(2600, 2800),
                 closes="2026-12-14", description="총무와 사무 지원", badges=[BADGE_NO_SOURCE]),
    ]


def build_companies() -> list[CompanyRecord]:
    def company(cid, name, badge, *, regional_talent=False, src=None):
        return CompanyRecord(company_id=cid, name=name, sido="26", highlights=[badge],
                             regional_talent=regional_talent, **(src or CHEONGGEUL_SRC))

    return [
        company("biz-DEMO000001", "(주)가상데이터", BADGE_CG_SALARY),
        company("biz-DEMO000002", "(주)가상상사", BADGE_CG_WORKLIFE),
        company("biz-DEMO000003", "(주)가상정밀", BADGE_GANGSO, src=GANGSO_SRC),
        company("biz-DEMO000101", "가상금융공사", BADGE_RELOCATED, regional_talent=True, src=RELOCATED_SRC),
        company("biz-DEMO000102", "가상주택금융공사", BADGE_RELOCATED, regional_talent=True, src=RELOCATED_SRC),
        company("biz-DEMO000103", "가상해양공단", BADGE_RELOCATED, regional_talent=True, src=RELOCATED_SRC),
    ]


BUSAN = PolicyRegion(scope=RegionScope.SIDO, sido="26")
SEOUL = PolicyRegion(scope=RegionScope.SIDO, sido="11")
NATION = PolicyRegion(scope=RegionScope.NATIONAL)
YOUTH = {"age_min": 18, "age_max": 39}

# 자주 쓰는 정책 ID
P_DIDIMDOL = "seed-busan-didimdol-plus"
P_INTERN = "seed-busan-job-matching-intern"
P_JOY_DOUBLE = "seed-busan-joy-double"
P_MOVING = "seed-busan-moving-cost"
P_STAY_LOAN = "seed-busan-stay-loan"
P_YOUTH_HOME = "seed-busan-youth-home"
P_UNVERIFIED = "seed-busan-unverified"
P_NATIONAL_JOB = "ythc-DEMO-N001"
P_NATIONAL_ASSET = "ythc-DEMO-N002"
P_BUSAN_INTERVIEW = "ythc-DEMO-B001"   # 부산, 상시, 자격만 맞으면 받음
P_BUSAN_RENT = "ythc-DEMO-B002"        # 부산, 소득 조건 있음 (T-13)
P_BUSAN_TRANSIT = "ythc-DEMO-B003"     # 부산, 만 23세부터 (demo1은 경계, T-12)
P_BUSAN_NAMGU = "ythc-DEMO-B004"       # 부산 남구만
P_SEOUL_ALLOWANCE = "ythc-DEMO-S001"
P_SEOUL_RENT = "ythc-DEMO-S002"


def build_policies() -> list[Policy]:
    def seed(pid, title, stage, *, summary, employment, public=None, self_share=None, selection=Selection.REVIEW,
             last=None, expected=None, period=PeriodType.FIXED, apply_end=None, exclusive=(), income=None,
             competition=None, verified=True, category="JOB"):
        return Policy(
            policy_id=pid, title=title, summary=summary, amount_max=public, age_min=18, age_max=39,
            residence_rule="부산 거주", income_rule=income.text if income else None,
            apply_start=last[0] if last else None,
            apply_end=apply_end or (last[1] if last else "9999-12-31"), url="https://example.invalid/busan-policy",
            source=PolicySource.BUSAN_SEED, as_of="2026-11-20", regions=[BUSAN], category=category, stage=stage,
            eligibility=PolicyEligibility(employment=employment, income=income, **YOUTH),
            benefit=PolicyBenefit(text=summary, public_share_max=public, self_share_max=self_share),
            application=PolicyApplication(period_type=period, selection=selection, last_competition=competition,
                                          expected=expected),
            last_cycle=PolicyCycle(start=last[0], end=last[1]) if last else None, exclusive_with=list(exclusive),
            checklist=["주민등록초본", "신청서"], verified=verified, verified_by="DEMO" if verified else None,
            verified_at="2026-11-20" if verified else None,
        )

    def ontong(pid, title, region, *, summary, public=None, selection=Selection.AUTOMATIC, apply=None,
               period=PeriodType.ALWAYS, age=(19, 34), employment=None, income=None, stage=PolicyStage.PREPARE,
               category="JOB"):
        return Policy(
            policy_id=pid, title=title, summary=summary, amount_max=public, age_min=age[0], age_max=age[1],
            apply_start=apply[0] if apply else None, apply_end=apply[1] if apply else "9999-12-31",
            url="https://example.invalid/youthcenter", source=PolicySource.YOUTHCENTER, as_of="2026-11-21",
            regions=[region], category=category, stage=stage, income_rule=income.text if income else None,
            eligibility=PolicyEligibility(age_min=age[0], age_max=age[1], employment=employment, income=income),
            benefit=PolicyBenefit(text=summary, public_share_max=public),
            application=PolicyApplication(period_type=period, selection=selection),
            verified=True, verified_by="YOUTHCENTER_API", verified_at="2026-11-21", youthcenter_id=pid[5:],
        )

    unemployed, employed = [EmploymentStatus.UNEMPLOYED], [EmploymentStatus.EMPLOYED]
    return [
        seed(P_DIDIMDOL, "디딤돌카드+", PolicyStage.PREPARE, summary="월 30만 원, 최대 6개월", employment=unemployed,
             public=180, last=("2026-03-02", "2026-03-20"), expected="2027년 상반기 (작년 3월 공지 기준)"),
        seed(P_INTERN, "청년 잡매칭 인턴", PolicyStage.PREPARE, summary="청끌기업 인턴, 정규직 전환 조건",
             employment=unemployed, last=("2026-02-02", "2026-02-27"), expected="2027년 상반기 (작년 2월 모집 기준)"),
        seed(P_JOY_DOUBLE, "부산청년 기쁨두배통장", PolicyStage.EMPLOYED, summary="월 10만 원 저축 시 시가 같은 금액 지원",
             employment=employed, public=360, self_share=360, selection=Selection.LOTTERY,
             last=("2026-08-10", "2026-08-21"), expected="2027년 8월 (작년 8.10~8.21 기준)",
             exclusive=("청년내일저축계좌",), competition="13:1 (2025)", category="ASSET"),
        seed(P_MOVING, "청년 중개보수·이사비 지원", PolicyStage.SETTLE, summary="실비 최대 40만 원, 생애 1회",
             employment=employed, public=40, last=("2026-08-18", "2026-08-24"),
             expected="2027년 8월 (작년 8.18~8.24 기준)", category="HOUSING"),
        seed(P_STAY_LOAN, "머물자리론", PolicyStage.SETTLE, summary="임차보증금 대출 이자 지원, 연 최대 250만 원",
             employment=None, public=250, selection=Selection.FIRST_COME, period=PeriodType.MONTHLY,
             income=IncomeRule(text="소득 기준 있음 (원문 확인)"), category="HOUSING"),
        seed(P_YOUTH_HOME, "청년모두가(家)", PolicyStage.SETTLE, summary="월 임대료에서 본인부담 3만 원을 뺀 금액 지원",
             employment=None, last=("2026-03-09", "2026-03-27"), expected="2027년 3월 (작년 3월 모집 기준)",
             category="HOUSING"),
        seed(P_UNVERIFIED, "검수 전 정책", PolicyStage.PREPARE, summary="원문 확인 전", employment=None, public=999,
             verified=False),
        ontong(P_NATIONAL_JOB, "[데모] 전국 구직활동 지원", NATION, summary="구직활동 지원금", public=300,
               selection=Selection.REVIEW, employment=unemployed),
        ontong(P_NATIONAL_ASSET, "[데모] 전국 청년 자산형성", NATION, summary="저축 지원", employment=employed,
               stage=PolicyStage.EMPLOYED, category="ASSET"),
        ontong(P_BUSAN_INTERVIEW, "[데모] 부산 청년 면접 지원", BUSAN, summary="면접 정장 대여와 교통비 10만 원",
               public=10, employment=unemployed),
        ontong(P_BUSAN_RENT, "[데모] 부산 청년 월세 지원", BUSAN, summary="월 20만 원, 최대 12개월", public=240,
               selection=Selection.REVIEW, income=IncomeRule(text="중위소득 60% 이하", max_household_level=60),
               stage=PolicyStage.SETTLE, category="HOUSING"),
        ontong(P_BUSAN_TRANSIT, "[데모] 부산 청년 교통비 지원", BUSAN, summary="월 5만 원", public=60, age=(23, 34)),
        ontong(P_BUSAN_NAMGU, "[데모] 부산 남구 청년 자격증 응시료 지원",
               PolicyRegion(scope=RegionScope.SIGUNGU, sido="26", sigungu="26290"), summary="응시료 최대 10만 원",
               public=10),
        ontong(P_SEOUL_ALLOWANCE, "[데모] 서울 청년 수당", SEOUL, summary="월 50만 원, 최대 6개월", public=300,
               selection=Selection.REVIEW, employment=unemployed, apply=("2026-11-02", "2026-11-27"),
               period=PeriodType.FIXED),
        ontong(P_SEOUL_RENT, "[데모] 서울 청년 월세 지원", SEOUL, summary="월 20만 원, 최대 12개월", public=240,
               selection=Selection.REVIEW, income=IncomeRule(text="중위소득 150% 이하", max_household_level=150),
               stage=PolicyStage.SETTLE, category="HOUSING"),
    ]


def build_profiles() -> dict[str, BasicProfile]:
    return {
        "demo1": BasicProfile(birth_year=2003, residence_sido="26", residence_sigungu="26290", university_region="26",
                              graduation_status="GRADUATING", education_level=EducationLevel.BACHELOR, major="통계학",
                              desired_jobs=[DesiredJob(work24_code="D0101", ncs_code="20010105", name="데이터 분석")],
                              employment_status=EmploymentStatus.UNEMPLOYED, priorities=["SALARY", "GROWTH"],
                              desired_region="ALL", is_demo=True),
        "demo2": BasicProfile(birth_year=1999, residence_sido="26", residence_sigungu="26380", university_region="26",
                              graduation_status="GRADUATED", education_level=EducationLevel.ASSOCIATE, major="경영학",
                              desired_jobs=[DesiredJob(work24_code="A0201", ncs_code="02030201", name="사무·회계")],
                              employment_status=EmploymentStatus.UNEMPLOYED, priorities=["STABILITY", "WORK_LIFE"],
                              desired_region="26", is_demo=True),
        "demo3": BasicProfile(birth_year=2001, residence_sido="26", residence_sigungu="26410", university_region="26",
                              graduation_status="GRADUATING", education_level=EducationLevel.BACHELOR, major="경제학",
                              desired_jobs=[DesiredJob(work24_code="F0101", name="공공기관 금융·행정")],
                              employment_status=EmploymentStatus.UNEMPLOYED, priorities=["STABILITY"],
                              desired_region="26", is_demo=True),
    }


def build_region_stats() -> RegionStats:
    """가짜 값이다. 실제 값은 국토교통부 실거래가를 받은 뒤 넣는다."""
    def rent(code, label, value, sample):
        return RentStat(region_code=code, label=label, value=value, sample_size=sample, period="2026-05~2026-10",
                        method="전용 33㎡ 이하, 환산 월세 = 월세 + 보증금 × 전환율 ÷ 12", source="데모 데이터",
                        as_of="2026-10")

    def commute(code, label, value):
        return CommuteStat(region_code=code, label=label, value=value, source="데모 데이터", as_of="2025")

    rents = [rent("11680", "서울 강남구", 95, 420), rent("11", "서울", 72, 9000), rent("26350", "부산 해운대구", 52, 180),
             rent("26290", "부산 남구", 45, 12), rent("26", "부산", 44, 3100), rent("41", "경기", 58, 7000)]
    commutes = [commute("11", "서울", 32.0), commute("26", "부산", 48.0), commute("41", "경기", 35.0)]
    return RegionStats(rent={r.region_code: r for r in rents}, commute={c.region_code: c for c in commutes})


def _test_eligibility(profile: dict, rules: list[dict]) -> dict:
    """`backend/eligibility.py`와 같은 계약의 대역. `ai/` 코드는 `backend/`를 import하지 않으므로 로컬·테스트에서 쓴다.

    배포에서는 백엔드가 진짜 함수를 `Deps.eligibility`로 넣는다.
    """
    order = {"NONE": 0, "HIGH_SCHOOL": 1, "ASSOCIATE": 2, "BACHELOR": 3, "MASTER": 4, "DOCTOR": 5}

    def norm(text):
        return "".join(str(text).lower().split())

    conditions = []
    for rule in rules or []:
        kind, value = rule.get("type"), rule.get("value")
        result, reason = "UNKNOWN", "직접 확인이 필요한 조건이에요"
        if kind == "EDUCATION":
            need, have = order.get(value or "NONE"), order.get(profile.get("educationLevel"))
            if need == 0:
                result, reason = "MET", "학력 무관"
            elif need is not None and have is not None:
                result, reason = ("MET", "학력 조건 충족") if have >= need else ("NOT_MET", "요구 학력보다 낮아요")
            else:
                reason = "프로필에 학력이 없어요"
        elif kind == "CAREER":
            value = value or {}
            if value.get("type") in ("NEW", "ANY", None):
                result, reason = "MET", "신입 지원 가능" if value.get("type") == "NEW" else "경력 무관"
            elif profile.get("careerYears") is not None:
                need = value.get("minYears") or 0
                ok = profile["careerYears"] >= need
                result, reason = ("MET", f"경력 {need}년 이상 충족") if ok else ("NOT_MET", f"경력 {need}년 이상이 필요해요")
            else:
                reason = "프로필에 경력 기간이 없어요"
        elif kind == "CERTIFICATE":
            have = {norm(c) for c in profile.get("certificates") or []}
            missing = {norm(c) for c in profile.get("confirmedMissingCertificates") or []}
            if norm(value) in have:
                result, reason = "MET", f"{value} 보유"
            elif norm(value) in missing:
                result, reason = "NOT_MET", f"{value}이(가) 필요해요"
            else:
                reason = f"{value} 보유 여부를 확인해 주세요"
        elif kind == "MAJOR":
            majors, mine = value or [], profile.get("major")
            if not majors:
                result, reason = "MET", "전공 무관"
            elif mine:
                ok = any(norm(m) in norm(mine) or norm(mine) in norm(m) for m in majors)
                result, reason = ("MET", "전공 조건 충족") if ok else ("NOT_MET", "요구 전공과 달라요")
            else:
                reason = "프로필에 전공이 없어요"
        conditions.append({"ruleId": rule.get("ruleId"), "type": kind, "result": result, "reason": reason,
                           "sourceQuote": rule.get("sourceQuote")})
    results = {c["result"] for c in conditions}
    if "NOT_MET" in results:
        status = "INELIGIBLE"
    elif not conditions or "UNKNOWN" in results:
        status = "NEEDS_VERIFICATION"
    else:
        status = "ELIGIBLE"
    return {"status": status, "conditions": conditions,
            "unknown": [c["ruleId"] for c in conditions if c["result"] == "UNKNOWN"], "ruleVersion": "elig-test"}


def build_deps(config: OpportunityConfig | None = None) -> Deps:
    """데모 데이터가 들어 있는 메모리 저장소로 Deps를 만든다. AWS를 부르지 않는다."""
    config = config or load_config()
    catalog, users, vectors, embedder = MemoryCatalog(), MemoryUsers(), MemoryVectors(), KeywordEmbedder()
    busan, capital = config.data.busan_sido, config.data.capital_area_sido
    for snap in build_snapshots():
        expired = snap.job_posting_id == BUSAN_DATA_EXPIRED
        latest = latest_from_snapshot(snap, busan_sido=busan, capital_sido=capital, is_expired=expired)
        catalog.put_snapshot(snap)
        catalog.put_latest(latest)
        sync_regional_index(catalog, None, latest)
        meta = VectorMeta(is_busan=latest.is_busan, sido=latest.work_region.sido or "", job_major=snap.job.major or "",
                          active=not expired, deadline=int(snap.closes_at.replace("-", "")), title=snap.title)
        vectors.put(snap.job_posting_id, embedder.embed(posting_text(snap)), meta.to_api())
    for base, candidates in ((SEOUL_DATA, [(BUSAN_DATA, 0.86), (BUSAN_DATA_PUBLIC, 0.81), (BUSAN_BACKEND, 0.52),
                                           (BUSAN_DATA_JUST_CLOSED, 0.9), (BUSAN_DATA_EXPIRED, 0.9)]),
                             (SEOUL_DATA_HYBRID, [(BUSAN_DATA, 0.84), (BUSAN_DATA_PUBLIC, 0.78)]),
                             (SEOUL_GAME, [(BUSAN_BACKEND, 0.41)])):
        catalog.put_alts(AltCandidates(job_posting_id=base, computed_at=DATA_AS_OF, candidates=[
            AltCandidate(job_posting_id=pid, similarity=sim) for pid, sim in candidates]))
    for policy in build_policies():
        catalog.put_policy(policy)
    for company in build_companies():
        catalog.put_company(company)
    catalog.set_data_as_of(DATA_AS_OF)
    users.profiles.update(build_profiles())
    return Deps(config=config, catalog=catalog, users=users, vectors=vectors, embedder=embedder,
                eligibility=_test_eligibility, workspaces=MemoryWorkspaces(), scheduler=MemoryScheduler(),
                events=MemoryEvents(), mailer=MemoryMailer(), region_stats=build_region_stats())
