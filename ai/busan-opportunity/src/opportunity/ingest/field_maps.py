"""출처별 "원본 필드 → 우리 필드" 매핑표와 호출 설정.

주의: 이 파일의 값은 전부 임시다. 공공 API의 실제 응답 필드 이름은 아직 아무도 확인하지 못했다
(개발계획서2 §3.2). 첫 수집이 `raw/{출처}/{날짜}/`에 남긴 원본 응답을 보고 이 표를 고친다.
정규화 함수(`normalize.py`)는 이 표만 본다. 필드 이름을 코드 안에 박지 않는다.

값 규칙
- 표의 값이 문자열이면 원본 키 하나, 튜플이면 앞에서부터 값이 있는 첫 키를 쓴다.
- 점이 든 경로(`a.b.c`)는 중첩된 값을 따라간다.
- 값이 None이면 그 출처에는 해당 필드가 없다는 뜻이다.
"""

from ..models.enums import PolicyStage

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

ALIO = {
    "source": "alio",
    "secret": SECRET_DATA_GO_KR,  # 공공데이터포털 키는 URL 인코딩된 값이다. `http.encode_key`가 두 번 인코딩하지 않는다
    "key_param": "serviceKey",
    "list": {
        "url": "https://apis.data.go.kr/1051000/recruitment/list",
        "params": {"resultType": "json"},
        "page_param": "pageNo", "size_param": "numOfRows", "page_size": 100, "first_page": 1, "max_pages": 50,
        "items_path": ("result", "response.body.items.item", "response.body.items"),
        "total_path": ("totalCount", "response.body.totalCount"),
    },
    "detail": {
        "url": "https://apis.data.go.kr/1051000/recruitment/detail",
        "params": {"resultType": "json"},
        "id_param": "sn", "item_path": ("result", "response.body.items.item", "response.body.items"),
    },
    "fields": {
        "external_id": "recrutPblntSn",
        "title": "recrutPbancTtl",
        "organization": "instNm",
        "region_code": None,
        "region_text": "workRgnNmLst",
        "job_code": None,
        "job_name": "ncsCdNmLst",
        "salary_kind": None,
        "salary_text": None,
        "employment_text": "hireTypeNmLst",
        "career_text": "recrutSeNm",
        "education_text": "acbgCondNmLst",
        "closes_text": "pbancEndYmd",
        "url": "srcUrl",
        "description": "recrutPbancCn",
        "selection_text": "scrnprcdrMthdExpln",
        "documents_text": None,
    },
}

YOUTHCENTER = {
    "source": "youthcenter",
    "secret": SECRET_YOUTHCENTER,
    "key_param": "apiKeyNm",
    "list": {
        "url": "https://www.youthcenter.go.kr/go/ythip/getPlcy",
        "params": {"rtnType": "json"},
        "page_param": "pageNum", "size_param": "pageSize", "page_size": 100, "first_page": 1, "max_pages": 50,
        "items_path": "result.youthPolicyList", "total_path": "result.pagging.totCount",
    },
    "fields": {
        "external_id": "plcyNo",
        "title": "plcyNm",
        "summary": "plcyExplnCn",
        "benefit_text": "plcySprtCn",
        "category": "lclsfNm",
        "age_min": "sprtTrgtMinAge",
        "age_max": "sprtTrgtMaxAge",
        "apply_period_text": "aplyYmd",
        "url": ("aplyUrlAddr", "refUrlAddr1"),
        "region_codes": "zipCd",          # 쉼표로 이어진 법정동 코드. 비어 있으면 전국
        "income_text": "earnEtcCn",
        "income_kind": "earnCndSeNm",
        "residence_text": None,
        "extra_conditions": ("addAplyQlfcCndCn", "ptcpPrpTrgtCn"),
        "apply_method": "plcyAplyMthdCn",
    },
}

SOURCES = {"work24": WORK24, "alio": ALIO, "youthcenter": YOUTHCENTER}

# 온통청년 대분류 이름 → Policy.category, 단계. 모르는 이름은 원문 그대로 category에 두고 단계는 기본값(PREPARE)을 쓴다.
CATEGORY_MAP = {"일자리": "JOB", "주거": "HOUSING", "교육": "EDUCATION", "복지문화": "WELFARE", "금융": "ASSET"}
STAGE_BY_CATEGORY = {"JOB": PolicyStage.PREPARE, "EDUCATION": PolicyStage.PREPARE, "HOUSING": PolicyStage.SETTLE}

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
