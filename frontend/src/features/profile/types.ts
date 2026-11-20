/** 기본 프로필 (`GET·PUT /api/v1/me/profile`). 이름·연락처는 받지 않는다. */
export type DesiredJob = { name: string; ncsCode?: string | null; work24Code?: string | null };

export type BasicProfile = {
  birthYear?: number;
  residenceSido?: string;
  residenceSigungu?: string;
  educationLevel?: string;
  graduationStatus?: string;
  employmentStatus?: string;
  major?: string;
  desiredJobs?: DesiredJob[];
  desiredRegion?: string;
  priorities?: string[];
  /** 채팅 조건 저장 (D-40): 희망 최소 연봉(만 원/년), 신입·경력 구분 */
  desiredSalaryMin?: number;
  desiredCareerType?: "NEW" | "EXPERIENCED" | "ANY";
};

/** 저장할 때 보내는 값. null은 그 항목을 지운다. */
export type BasicProfileInput = { [K in keyof BasicProfile]: BasicProfile[K] | null };
