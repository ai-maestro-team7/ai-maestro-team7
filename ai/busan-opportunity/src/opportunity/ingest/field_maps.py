"""출처별 "원본 필드 → 우리 필드" 매핑표와 호출 설정.

확인 상태 (2026-11-20, 개발계획서2 §3.2)
- 온통청년 청년정책, 고용24 청년일자리강소기업, 고용24 공통코드(지역·직종): 실제 응답을 받아 이 표를 맞췄다.
  원본은 `raw/{출처}/2026-11-20/`에 있다.
- 잡알리오 채용공시(ALIO): 실제 응답(목록 563건, 상세 1건)을 받아 맞췄다.
- 고용24 채용정보(WORK24): 응답 미확인. 값은 응답을 보기 전에 넣은 임시 값이다.
정규화 함수(`normalize.py`)는 이 표만 본다. 필드 이름을 코드 안에 박지 않는다.

값 규칙
- 표의 값이 문자열이면 원본 키 하나, 튜플이면 앞에서부터 값이 있는 첫 키를 쓴다.
- 점이 든 경로(`a.b.c`)는 중첩된 값을 따라간다.
- 값이 None이면 그 출처에는 해당 필드가 없다는 뜻이다.
"""

from ..models.enums import CareerType, EducationLevel, EmploymentType, PolicyStage

# 호출 정책. 명세에 정해진 값이고 설정 파일에는 아직 자리가 없다 (공용 파일 변경 요청).
HTTP_TIMEOUT_SECONDS = 5      # 개발계획서2 §4.2 B-01, 강의 안내: 외부 API는 타임아웃 5초
MAX_RETRIES = 3               # 실패한 페이지는 지수 백오프로 3번까지 다시 부른다
BACKOFF_BASE_SECONDS = 1.0    # 대기 시간 = 기준 * 2**(시도 횟수)
SECRET_CACHE_SECONDS = 300    # 인증키는 5분 캐시한다
DETAIL_MAX_PER_RUN = 300      # 일일 한도를 확인하기 전까지 상세 호출에 거는 임시 상한

# 인증키 이름 (Secrets Manager). 환경변수 이름은 지식 패키지 `collect_official_apis.py`를 따랐다.
SECRET_DATA_GO_KR = "DATA_GO_KR_SERVICE_KEY"
SECRET_WORK24 = "WORK24_AUTH_KEY"
SECRET_YOUTHCENTER = "YOUTHCENTER_API_KEY"
SECRET_WORK24_GANGSO = "WORK24_GANGSO_KEY"  # 고용24는 서비스마다 인증키가 따로다
SECRET_WORK24_CODES = "WORK24_CODES_KEY"

# 응답 미확인 (개인회원 불가): 고용24 채용정보 목록 210L01·상세 210D01은 개인회원 키로 부르면
# "개인회원은 사용할 수 없는 OPEN-API입니다" 오류가 온다 (2026-11-20). 아래 필드 이름은 임시 값이다.
WORK24 = {
    "source": "work24",
    "secret": SECRET_WORK24,
    "key_param": "authKey",
    "list": {
        "url": "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do",
        "params": {"callTp": "L", "returnType": "XML"},
        "page_param": "startPage", "size_param": "display", "page_size": 100, "first_page": 1, "max_pages": 50,
        "items_path": "wantedRoot.wanted", "total_path": "wantedRoot.total",
    },
    "detail": {
        "url": "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210D01.do",
        "params": {"callTp": "D", "returnType": "XML"},
        "id_param": "wantedAuthNo", "item_path": "wantedDtl.wantedInfo",
    },
    "fields": {
        "external_id": "wantedAuthNo",
        "title": "title",
        "organization": "company",
        "region_code": None,
        "region_text": ("basicAddr", "region"),
        "job_code": "jobsCd",
        "job_name": "jobsNm",
        "salary_kind": "salTpNm",
        "salary_text": "sal",
        "employment_text": "empTpNm",
        "career_text": "career",
        "education_text": "minEdubg",
        "closes_text": "closeDt",
        "url": "wantedInfoUrl",
        "description": "jobCont",
        "selection_text": "selMthd",
        "documents_text": "submitDoc",
    },
}

# 잡알리오 채용공시 (2026-11-20 응답 확인). 진행 중 공고(ongoingYn=Y)는 563건, 100건씩 6페이지다.
# 응답: {"resultCode": 200, "resultMsg", "totalCount", "result": [...]}. 상세는 result가 목록이 아니라 객체 하나다.
# 목록과 상세의 필드가 같고 목록에도 지원 자격·우대·전형 글이 다 온다. 다른 점은 상세에만 files·steps가 차 있다는 것.
# 그래서 상세는 기본으로 부르지 않는다 (`detail.enabled`).
ALIO = {
    "source": "alio",
    "secret": SECRET_DATA_GO_KR,  # 공공데이터포털 키는 URL 인코딩된 값이다. `http.encode_key`가 두 번 인코딩하지 않는다
    "key_param": "serviceKey",
    "list": {
        "url": "https://apis.data.go.kr/1051000/recruitment/list",
        "params": {"resultType": "json", "ongoingYn": "Y"},
        "page_param": "pageNo", "size_param": "numOfRows", "page_size": 100, "first_page": 1, "max_pages": 50,
        "items_path": "result", "total_path": "totalCount",
    },
    "detail": {
        "enabled": False,  # True로 바꾸면 수집 실행기가 부산·수도권 공고의 상세(첨부 파일 이름)를 부른다
        "url": "https://apis.data.go.kr/1051000/recruitment/detail",
        "params": {"resultType": "json"},
        "id_param": "sn", "item_path": "result",
    },
    "fields": {
        "external_id": "recrutPblntSn",       # 숫자로 온다 (307285)
        "title": "recrutPbancTtl",
        "organization": "instNm",
        "region_names": "workRgnNmLst",       # "대구,인천,…,전남광주". 코드(workRgnLst R3013 등)는 잡알리오 자체 코드다
        "ncs_codes": "ncsCdLst",              # "R600001,R600002". NCS 대분류에 대응하는 잡알리오 코드
        "ncs_names": "ncsCdNmLst",            # "사업관리,경영.회계.사무"
        "employment_names": "hireTypeNmLst",  # "비정규직,청년인턴(체험형)"
        "career_name": "recrutSeNm",          # 신입 / 경력 / 신입+경력
        "education_names": "acbgCondNmLst",   # "학력무관,고졸,대졸(2~3년),대졸(4년),석사,박사"
        "closes_ymd": "pbancEndYmd",          # "20261204"
        "url": "srcUrl",                      # 기관 누리집. "없음", ".", "www.ex.co.kr"처럼 오기도 한다
        "qualification": "aplyQlfcCn",        # 지원 자격
        "preference": "prefCn",               # 우대 내용 (가점)
        "preference_targets": "prefCondCn",   # 우대 대상 목록
        "selection": "scrnprcdrMthdExpln",    # 전형 절차·방법
        "files": "files",                     # 상세에만 온다. [{atchFileNm, atchFileType, url, sortNo}]
        "file_name": "atchFileNm",
        "steps": "steps",                     # 상세에만 온다. 아래 설명 참고
    },
}
# 고용 형태 이름 → EmploymentType (2026-11-20 응답의 값 5종이 전부다). 여러 개가 섞이면 UNKNOWN이다.
ALIO_EMPLOYMENT = {
    "정규직": EmploymentType.FULL_TIME,
    "무기계약직": EmploymentType.CONTRACT,
    "비정규직": EmploymentType.CONTRACT,
    "기간제": EmploymentType.CONTRACT,
    "청년인턴(체험형)": EmploymentType.INTERN,
    "청년인턴(채용형)": EmploymentType.INTERN,
}
# 채용 구분 → CareerType (값 3종)
ALIO_CAREER = {"신입": CareerType.NEW, "경력": CareerType.EXPERIENCED, "신입+경력": CareerType.ANY,
               "무관": CareerType.ANY}
# 학력 조건 이름 → EducationLevel (값 6종). 여러 개면 가장 낮은 것이 최소 학력이다.
ALIO_EDUCATION = {
    "학력무관": EducationLevel.NONE,
    "고졸": EducationLevel.HIGH_SCHOOL,
    "대졸(2~3년)": EducationLevel.ASSOCIATE,
    "대졸(4년)": EducationLevel.BACHELOR,
    "석사": EducationLevel.MASTER,
    "박사": EducationLevel.DOCTOR,
}
# 근무지 이름 가운데 시·도가 아닌 것. "전국"은 근무지를 하나로 정할 수 없어 unknown으로 둔다.
# 응답에 "해외"가 2건 있다. 표에 없는 이름은 시·도로 세지 않고 "외 N개 지역"의 N에만 넣는다.
ALIO_NATIONAL_NAMES = {"전국"}
ALIO_JOB_NAME_SHOWN = 2       # 직무 이름에 보여 줄 NCS 분류 수. 나머지는 "외 N"으로 줄인다
ALIO_ROLLING_MIN_DAYS = 365   # 마감일이 이만큼 넘게 남았으면 상시 채용으로 본다 (응답에 20271231·20501231이 있다)
ALIO_ROLLING_TITLE_WORDS = ("상시",)
# steps는 분야마다 단계 행이 3개씩 오는데(recrutPbancTtl="차량", minStepSn~maxStepSn) 단계 이름이 없다.
# 그래서 selectionSteps는 steps로 만들지 않고 전형 글(scrnprcdrMthdExpln)을 보강(enrich)이 읽게 둔다.
# 기관 누리집 칸에서 버릴 값 (주소가 아닌 값)
ALIO_URL_BLANKS = {"없음", "없음.", "해당없음", ".", ",", "/", "-", "com"}

# 온통청년 청년정책 (2026-11-20 응답 확인). pageType=1이 없으면 e003 오류가 온다.
# 응답: result.pagging.totCount, result.youthPolicyList[]. 3,996건이라 100건씩 40페이지다.
YOUTHCENTER = {
    "source": "youthcenter",
    "secret": SECRET_YOUTHCENTER,
    "key_param": "apiKeyNm",
    "list": {
        "url": "https://www.youthcenter.go.kr/go/ythip/getPlcy",
        "params": {"pageType": 1, "rtnType": "json"},
        "page_param": "pageNum", "size_param": "pageSize", "page_size": 100, "first_page": 1, "max_pages": 60,
        "items_path": "result.youthPolicyList", "total_path": "result.pagging.totCount",
    },
    "fields": {
        "external_id": "plcyNo",
        "title": "plcyNm",
        "summary": ("plcySprtCn", "plcyExplnCn"),  # 지원 내용 원문이 먼저, 없으면 정책 설명
        "benefit_text": "plcySprtCn",
        "category": "lclsfNm",                     # 대분류. "일자리,교육"처럼 여럿이 쉼표로 올 수 있다
        "subcategory": "mclsfNm",                  # 중분류
        "age_limited": "sprtTrgtAgeLmtYn",         # Y일 때만 나이를 쓴다
        "age_min": "sprtTrgtMinAge",
        "age_max": "sprtTrgtMaxAge",
        "apply_period_code": "aplyPrdSeCd",
        "apply_period_text": "aplyYmd",            # "20261119 ~ 20261204". 여러 기간은 글자 \N으로 이어 온다
        "biz_start": "bizPrdBgngYmd",
        "biz_end": "bizPrdEndYmd",
        "url": ("aplyUrlAddr", "refUrlAddr1"),
        "region_codes": "zipCd",                   # 법정 시군구 코드 5자리를 쉼표로 이은 값
        "income_code": "earnCndSeCd",
        "income_min": "earnMinAmt",
        "income_max": "earnMaxAmt",
        "income_text": "earnEtcCn",
        "extra_conditions": "addAplyQlfcCndCn",    # 추가 자격 조건
        "excluded_targets": "ptcpPrpTrgtCn",       # 참여 제한 대상
        "first_come": "sprtArvlSeqYn",             # Y면 선착순
        "documents": "sbmsnDcmntCn",
        "job_codes": "jobCd",
    },
}

# 온통청년 코드 값. 공식 코드표를 아직 못 봐서 2026-11-20 응답 3,996건의 분포로 추정했다.
# 신청기간구분 (aplyPrdSeCd)
APPLY_PERIOD_FIXED = "0057001"    # 추정: 특정 기간. 이 값만 aplyYmd가 채워져 온다 (1,938건 모두)
APPLY_PERIOD_ALWAYS = "0057002"   # 추정: 상시. aplyYmd가 늘 비어 있고 사업 기간 대부분이 아직 진행 중이다
APPLY_PERIOD_CLOSED = "0057003"   # 추정: 마감. aplyYmd가 비어 있고 사업 기간 80%가 이미 끝났다
# 소득조건구분 (earnCndSeCd)
INCOME_ANY = "0043001"            # 추정: 무관. 금액이 모두 0이고 기타 내용이 없다
INCOME_AMOUNT = "0043002"         # 추정: 연소득 금액 조건. earnMinAmt·earnMaxAmt가 채워져 온다
INCOME_OTHER = "0043003"          # 추정: 기타. earnEtcCn에 "중위소득 150% 이하" 같은 글이 온다
# 나이 제한 여부 (sprtTrgtAgeLmtYn). 응답 분포가 "Y면 제한 있음"과 맞지 않는다.
#   Y 1,800건 중 1,050건이 나이 0/0이고(예: 출산가정 산후조리비용 지원),
#   N 2,196건 중 2,121건이 나이를 담고 있으며 그중 757건은 글에도 같은 상한 나이가 나온다(예: 청년참여기구 19~39세).
# 그래서 여부 값과 상관없이 0이 아닌 나이를 쓴다 (0은 제한 없음). True로 바꾸면 Y일 때만 나이를 쓴다.
AGE_ONLY_WHEN_LIMIT_FLAG_Y = False
# earnMinAmt·earnMaxAmt의 단위. 추정: 만 원 (조건 글 "연소득 5천만원"인 정책의 최대값이 5000).
# 확실하지 않아 숫자 판정에는 쓰지 않고 안내 글에만 쓴다.
INCOME_AMOUNT_UNIT_LABEL = "만 원"
# jobCd(취업 상태) 코드는 뜻을 확인하지 못했다. employment 조건은 만들지 않는다 (None = 제한 없음).

# 자유 서술 칸에서 "조건 없음"으로 보는 값. 이 값이면 조건으로 옮기지 않는다
BLANK_CONDITION_TEXTS = {"-", "--", "해당 없음", "해당없음", "없음", "제한 없음", "제한없음", "무관", "x", "X"}

# 정책 지역 규칙 (zipCd)
NATIONAL_MIN_SIDO = 15  # 시·도가 이만큼 이상이면 전국 정책으로 본다 (2026년 시·도는 16곳)
# 2026년 전남·광주 통합으로 생긴 시·도 코드. 고용24 지역 코드(CMCD_1)와 온통청년 zipCd에 나온다.
# 공용 `core/regions.SIDO_NAMES`에 아직 없어서 수집 쪽에서만 더해 쓴다 (공용 파일 변경 요청).
EXTRA_SIDO_NAMES = {"12": "전남광주"}

# 고용24 청년일자리강소기업 (2026-11-20 응답 확인). 지역마다 따로 부른다 (region=26000 등).
# 응답: smallGiantsList > total, smallGiant[]
WORK24_GANGSO = {
    "source": "work24_gangso",
    "secret": SECRET_WORK24_GANGSO,
    "key_param": "authKey",
    "list": {
        "url": "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo216L01.do",
        "params": {"returnType": "XML"},
        "page_param": "startPage", "size_param": "display", "page_size": 100, "first_page": 1, "max_pages": 60,
        "items_path": "smallGiantsList.smallGiant", "total_path": "smallGiantsList.total",
    },
    "region_param": "region",  # 시·도 코드 + "000" (부산 26000)
    "fields": {
        "biz_no": "busiNo",
        "name": "coNm",
        "brand": "sgBrandNm",
        "year": "selYear",
        "region_code": "regionCd",
        "industry": ("indTpNm", "superIndTpNm"),
        "workers": "alwaysWorkerCnt",
    },
}
GANGSO_BADGE_SOURCE = "고용노동부 청년일자리강소기업"
COMPANY_ID_PREFIX = "biz"

SOURCES = {"work24": WORK24, "alio": ALIO, "youthcenter": YOUTHCENTER, "work24_gangso": WORK24_GANGSO}

# 온통청년 대분류 이름 → Policy.category. 여기 없는 이름은 원문 그대로 category에 둔다.
CATEGORY_MAP = {"일자리": "JOB", "주거": "HOUSING"}
STAGE_BY_CATEGORY = {"JOB": PolicyStage.PREPARE, "HOUSING": PolicyStage.SETTLE}
# 중분류가 이 이름이면 대분류보다 먼저 단계를 정한다. 중분류 "재직자"는 취업한 청년 대상이다
STAGE_BY_SUBCATEGORY = {"재직자": PolicyStage.EMPLOYED}

# 근무지 글에서 시·도를 알아볼 이름 (첫 낱말). 시·도 번호는 법정동 코드 앞 2자리다.
SIDO_ALIASES = {
    "서울": "11", "서울시": "11", "서울특별시": "11",
    "부산": "26", "부산시": "26", "부산광역시": "26",
    "대구": "27", "대구시": "27", "대구광역시": "27",
    "인천": "28", "인천시": "28", "인천광역시": "28",
    "광주": "29", "광주광역시": "29",
    "대전": "30", "대전시": "30", "대전광역시": "30",
    "울산": "31", "울산시": "31", "울산광역시": "31",
    "세종": "36", "세종시": "36", "세종특별자치시": "36",
    "경기": "41", "경기도": "41",
    "충북": "43", "충청북도": "43",
    "충남": "44", "충청남도": "44",
    "전남": "46", "전라남도": "46",
    "경북": "47", "경상북도": "47",
    "경남": "48", "경상남도": "48",
    "제주": "50", "제주도": "50", "제주특별자치도": "50",
    "강원": "51", "강원도": "51", "강원특별자치도": "51",
    "전북": "52", "전라북도": "52", "전북특별자치도": "52",
}
