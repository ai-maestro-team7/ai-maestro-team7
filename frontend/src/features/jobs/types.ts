/**
 * B 부산 기회 추천 API 응답 (`/api/v1/opportunities/postings*`, 카멜 표기).
 * 기준: `ai/busan-opportunity/src/opportunity/models/api.py`. 서버가 null 필드를 빼고 보내므로 선택 필드가 많다.
 */

/** 공고 적합도 3단계 (B matchScore를 화면에서는 말로만 보여준다, docs/api.md §6.3) */
export type MatchLevel = "GOOD" | "FAIR" | "LOW";

export type OrgType = "PRIVATE" | "PUBLIC_INSTITUTION" | "LOCAL_PUBLIC";
export type EmploymentType = "FULL_TIME" | "CONTRACT" | "PART_TIME" | "INTERN" | "UNKNOWN";
export type CareerType = "NEW" | "EXPERIENCED" | "ANY" | "UNKNOWN";
export type MoneyUnit = "MANWON_YEAR" | "MANWON_MONTH" | "MANWON" | "WON";

/** 피드 정렬 (B `Sort`). 화면에서는 부산 우선 추천순과 마감순만 고른다. */
export type JobSort = "BUSAN_FIRST" | "DEADLINE";
/** 피드 지역 필터 (B `region`) */
export type JobRegion = "ALL" | "BUSAN" | "CAPITAL" | "OVERSEAS";
/** 기관 구분 필터 (B `sector`): 공기업 = 공공기관·지방공공기관, 사기업 = 민간 기업 */
export type JobSector = "ALL" | "PUBLIC" | "PRIVATE";
/** 경력 필터. 신입·경력 무관 공고는 둘 다에 보인다 */
export type CareerFilter = "ALL" | "NEW" | "EXPERIENCED";
export type EmploymentFilter = "ALL" | "FULL_TIME" | "CONTRACT" | "INTERN";

export type WorkRegion = {
  sido?: string;
  sigungu?: string;
  label: string;
  unknown: boolean;
  overseas: boolean;
};

export type Badge = {
  type: string;
  label: string;
  source: string;
  asOf: string;
};

export type Salary = {
  disclosed: boolean;
  min?: number;
  max?: number;
  unit: MoneyUnit;
};

export type EligibilityCondition = {
  ruleId: string;
  type: string;
  result: "MET" | "NOT_MET" | "UNKNOWN";
  reason: string;
  sourceQuote?: string;
};

export type PostingEligibility = {
  status: "ELIGIBLE" | "INELIGIBLE" | "NEEDS_VERIFICATION";
  conditions: EligibilityCondition[];
  ruleVersion?: string;
};

export type JobInfo = { code?: string; name?: string; major?: string };

/** 피드 카드 (`PostingCard`) */
export type PostingCard = {
  jobPostingId: string;
  title: string;
  organization: string;
  orgType: OrgType;
  workRegion: WorkRegion;
  isBusan: boolean;
  isCapitalArea: boolean;
  job: JobInfo;
  closesAt: string;
  rolling: boolean;
  salary?: Salary;
  matchLevel: MatchLevel;
  eligibility?: PostingEligibility;
  badges: Badge[];
  facts: string[];
  /** 수도권 공고에만 */
  busanAlternativesCount?: number;
  /** 지역 조건: LIKELY(학교 지역·사는 곳이 맞아 대상일 수 있음), CHECK_NEEDED(맞는지 공고문 확인). 해당 없으면 없음 */
  regionalTalent?: "LIKELY" | "CHECK_NEEDED";
  isSample: boolean;
};

export type FeedResponse = {
  items: PostingCard[];
  ranking: { sort: string; basis: string };
  dataAsOf?: string;
  stale: boolean;
  nextCursor?: string;
  emptyMessage?: string;
};

export type Requirement = {
  requirementId: string;
  name: string;
  kind: "REQUIRED_SKILL" | "PREFERRED_SKILL";
  sourceQuote?: string;
};

export type PostingSnapshot = {
  jobPostingId: string;
  title: string;
  organization: string;
  jobDescription?: string;
  requirements: Requirement[];
  closesAt: string;
  rolling: boolean;
  officialUrl?: string;
  sourceType: "OFFICIAL" | "DEMO";
  checkedAt?: string;
  source: string;
  orgType: OrgType;
  workRegion: WorkRegion;
  job: JobInfo;
  employmentType?: EmploymentType;
  careerType?: CareerType;
  salary?: Salary;
  extractStatus?: "PENDING" | "DONE" | "FAILED";
};

export type AlternativeItem = {
  jobPostingId: string;
  title: string;
  organization: string;
  workRegion: WorkRegion;
  closesAt: string;
  matchLevel: MatchLevel;
  badges: Badge[];
  facts: string[];
  whyShown: string;
  isSample: boolean;
};

export type PolicyBrief = {
  policyId: string;
  title: string;
  bucket: string;
  status: string;
  summary?: string;
};

export type PostingDetailResponse = {
  posting: PostingSnapshot;
  isBusan: boolean;
  isCapitalArea: boolean;
  closed: boolean;
  isSample: boolean;
  matchLevel?: MatchLevel;
  eligibility: PostingEligibility;
  badges: Badge[];
  regionalTalent?: { status: "LIKELY" | "CHECK_NEEDED" | "NOT_APPLICABLE"; message?: string };
  relatedPolicies: PolicyBrief[];
  alternativesPreview: AlternativeItem[];
  facts: string[];
  dataAsOf?: string;
};

/** 로그인 없이 보는 공고 한 줄 (`PublicPostingCard`). 적합도·자격 판정 같은 개인 값이 없다. */
export type PublicPostingCard = {
  jobPostingId: string;
  title: string;
  organization: string;
  orgType: OrgType;
  workRegion: WorkRegion;
  isBusan: boolean;
  isOverseas: boolean;
  job: JobInfo;
  closesAt: string;
  rolling: boolean;
  salary?: Salary;
  careerType: CareerType;
  employmentType: EmploymentType;
  badges: Badge[];
  isSample: boolean;
};

/** `GET /api/v1/opportunities/public/postings`. total은 분류·검색어에 맞는 진행 중 공고 수(모든 쪽 합)다. */
export type PublicPostingList = {
  items: PublicPostingCard[];
  total: number;
  nextCursor?: string;
  dataAsOf?: string;
  stale: boolean;
};

