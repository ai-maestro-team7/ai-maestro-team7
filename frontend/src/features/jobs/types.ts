export type EmploymentType = "정규직" | "계약직" | "인턴";

/** 공고 적합도 3단계 (B matchScore를 화면에서는 말로만 보여준다, docs/api.md §6.3) */
export type MatchLevel = "GOOD" | "FAIR" | "LOW";

export type JobPosting = {
  id: string;
  company: string;
  /** 로고 자리에 보여줄 첫 글자 */
  companyInitial: string;
  companyNote: string;
  title: string;
  skills: string[];
  /** 부산 구·군 (예: "해운대구") */
  district: string;
  employmentType: EmploymentType;
  careerLevel: string;
  /** 마감일 (YYYY-MM-DD). 상시 채용이면 null */
  deadline: string | null;
  match: {
    level: MatchLevel;
    /** 표에 보이는 짧은 근거 (예: "Python, REST API 일치") */
    reason: string;
  };
  /** 추천순(부산 우선) 순위. 작을수록 먼저 */
  recommendRank: number;
  duties: string[];
  requirements: string[];
  matchedSkills: string[];
  gapAdvice: string;
  applyNote: string;
};

export type JobTypeFilter = "전체" | EmploymentType;
export type JobSort = "RECOMMENDED" | "DEADLINE";
