/**
 * 기본 프로필 입력 선택지. 값은 백엔드 `PUT /api/v1/me/profile` (backend/me_api.py)가 받는 것과 같다.
 */
export const SIDO_OPTIONS = [
  { value: "26", label: "부산" },
  { value: "11", label: "서울" },
  { value: "27", label: "대구" },
  { value: "28", label: "인천" },
  { value: "29", label: "광주" },
  { value: "30", label: "대전" },
  { value: "31", label: "울산" },
  { value: "36", label: "세종" },
  { value: "41", label: "경기" },
  { value: "51", label: "강원" },
  { value: "43", label: "충북" },
  { value: "44", label: "충남" },
  { value: "52", label: "전북" },
  { value: "46", label: "전남" },
  { value: "47", label: "경북" },
  { value: "48", label: "경남" },
  { value: "50", label: "제주" },
] as const;

/** 부산 구·군 (행정구역 코드 5자리). 통근 시간과 구 단위 정책 판정에 쓴다. */
export const BUSAN_SIGUNGU_OPTIONS = [
  { value: "26110", label: "중구" },
  { value: "26140", label: "서구" },
  { value: "26170", label: "동구" },
  { value: "26200", label: "영도구" },
  { value: "26230", label: "부산진구" },
  { value: "26260", label: "동래구" },
  { value: "26290", label: "남구" },
  { value: "26320", label: "북구" },
  { value: "26350", label: "해운대구" },
  { value: "26380", label: "사하구" },
  { value: "26410", label: "금정구" },
  { value: "26440", label: "강서구" },
  { value: "26470", label: "연제구" },
  { value: "26500", label: "수영구" },
  { value: "26530", label: "사상구" },
  { value: "26710", label: "기장군" },
] as const;

export const BUSAN_SIDO = "26";

export const EDUCATION_OPTIONS = [
  { value: "HIGH_SCHOOL", label: "고등학교" },
  { value: "ASSOCIATE", label: "전문대" },
  { value: "BACHELOR", label: "대학교" },
  { value: "MASTER", label: "석사" },
  { value: "DOCTOR", label: "박사" },
] as const;

/** 전문대 이상이면 대학 이름을 받는다. 고졸이면 학교 지역(고등학교)만 받는다 */
export const HIGHER_EDUCATION: ReadonlySet<string> = new Set(["ASSOCIATE", "BACHELOR", "MASTER", "DOCTOR"]);
/** 대학원까지 마쳤으면 지역인재는 학부 대학 소재지로 본다 */
export const GRADUATE_SCHOOL: ReadonlySet<string> = new Set(["MASTER", "DOCTOR"]);

/** 가진 자격증: 백엔드 `certificates`가 받는 한도 (backend/me_api.py) */
export const MAX_CERTIFICATES = 10;
export const CERTIFICATE_MAX_LENGTH = 50;

export const GRADUATION_OPTIONS = [
  { value: "ENROLLED", label: "재학 중" },
  { value: "GRADUATING", label: "졸업 예정" },
  { value: "GRADUATED", label: "졸업" },
] as const;

export const EMPLOYMENT_OPTIONS = [
  { value: "UNEMPLOYED", label: "구직 중" },
  { value: "STUDENT", label: "학생" },
  { value: "PART_TIME", label: "단기·시간제 근무" },
  { value: "EMPLOYED", label: "재직 중" },
] as const;

/**
 * 희망 분야 (NCS 대분류 24개). `value`는 공공기관 공고에 적힌 분류 이름 그대로다 (가운뎃점 대신 마침표).
 * 공고의 분류 이름과 글자로 비교하므로 바꾸지 않는다.
 */
export const JOB_FIELD_OPTIONS = [
  { value: "경영.회계.사무", label: "경영·회계·사무" },
  { value: "사업관리", label: "사업관리" },
  { value: "금융.보험", label: "금융·보험" },
  { value: "정보통신", label: "정보통신" },
  { value: "전기.전자", label: "전기·전자" },
  { value: "기계", label: "기계" },
  { value: "건설", label: "건설" },
  { value: "재료", label: "재료" },
  { value: "화학.바이오", label: "화학·바이오" },
  { value: "환경.에너지.안전", label: "환경·에너지·안전" },
  { value: "보건.의료", label: "보건·의료" },
  { value: "사회복지.종교", label: "사회복지·종교" },
  { value: "교육.자연.사회과학", label: "교육·자연·사회과학" },
  { value: "법률.경찰.소방.교도.국방", label: "법률·경찰·소방·교도·국방" },
  { value: "문화.예술.디자인.방송", label: "문화·예술·디자인·방송" },
  { value: "영업판매", label: "영업판매" },
  { value: "운전.운송", label: "운전·운송" },
  { value: "경비.청소", label: "경비·청소" },
  { value: "이용.숙박.여행.오락.스포츠", label: "이용·숙박·여행·오락·스포츠" },
  { value: "음식서비스", label: "음식서비스" },
  { value: "식품가공", label: "식품가공" },
  { value: "섬유.의복", label: "섬유·의복" },
  { value: "인쇄.목재.가구.공예", label: "인쇄·목재·가구·공예" },
  { value: "농림어업", label: "농림어업" },
] as const;

export const PRIORITY_OPTIONS = [
  { value: "SALARY", label: "연봉" },
  { value: "GROWTH", label: "성장" },
  { value: "STABILITY", label: "안정" },
  { value: "WORK_LIFE", label: "워라밸" },
  { value: "HOUSING", label: "주거" },
  { value: "LOCATION", label: "위치" },
] as const;

export const MAX_PRIORITIES = 3;
