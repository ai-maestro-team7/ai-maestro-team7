import type { JobPosting } from "./types";

/** Mock 데이터 기준일. B 데모 데이터(`ai/busan-opportunity` seeds `DATA_AS_OF`)와 같은 날이다. */
export const DATA_AS_OF = "2026-11-21";

/**
 * 추천 기준 프로필 표시 (공고 목록 상단).
 * 통합 데모 페르소나 ①: 부산 소재 대학 4학년, 통계학 전공, 희망 직무 데이터 분석 (NCS 20010105, D-37).
 */
export const RECOMMEND_BASIS = {
  role: "데이터 분석",
  skills: ["SQL", "Python", "통계 분석"],
} as const;

/**
 * 시연용 예시 공고. 기업·기관과 공고는 모두 가상이고, B 데모 데이터
 * (`ai/busan-opportunity/src/opportunity/seeds/demo_world.py`)의 부산 공고와 이름·근무지·마감·요건을 맞췄다.
 * 업무 설명은 같은 공고의 직무 설명을 화면용으로 나눈 예시다.
 */
export const jobPostings: JobPosting[] = [
  {
    id: "wk24-DEMO0001",
    company: "(주)가상데이터",
    companyInitial: "데",
    companyNote: "시연용 예시 기업",
    title: "데이터 분석 신입",
    skills: ["SQL", "Python"],
    district: "해운대구",
    employmentType: "정규직",
    careerLevel: "신입",
    deadline: "2026-12-05",
    match: { level: "GOOD", reason: "SQL, Python 일치" },
    recommendRank: 1,
    duties: ["서비스 지표 분석과 리포트 작성", "SQL로 데이터 추출과 가공", "통계 모델링으로 사용자 행동 분석"],
    requirements: ["SQL 활용 (필수)", "Python 활용 (필수)", "ADsP (우대)"],
    matchedSkills: ["SQL", "Python", "통계 분석"],
    gapAdvice: "우대 자격인 ADsP 준비 계획이 있다면 이력서에 적어 보세요.",
    applyNote: "시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
  {
    id: "alio-DEMO0001",
    company: "가상금융공사",
    companyInitial: "금",
    companyNote: "시연용 예시 기관 · 부산 이전 공공기관",
    title: "2026년 신입직원 채용 (데이터)",
    skills: ["통계 분석", "SQL"],
    district: "남구",
    employmentType: "정규직",
    careerLevel: "신입",
    deadline: "2026-11-30",
    match: { level: "FAIR", reason: "통계 분석 일치" },
    recommendRank: 2,
    duties: ["기금 운용 데이터 분석", "통계 분석으로 운용 지표 점검", "분석 결과 보고서 작성"],
    requirements: ["통계 분석 (필수)", "SQL (우대)"],
    matchedSkills: ["통계 분석", "SQL"],
    gapAdvice: "기금·금융 데이터를 다뤄 본 경험이 있다면 사례로 정리해 보세요.",
    applyNote:
      "지역인재 전형 대상일 수 있어요 · 공고문 확인. 시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
  {
    id: "wk24-DEMO0012",
    company: "(주)가상소프트",
    companyInitial: "소",
    companyNote: "시연용 예시 기업",
    title: "백엔드 개발자",
    skills: ["Python"],
    district: "해운대구",
    employmentType: "정규직",
    careerLevel: "신입",
    deadline: "2026-12-11",
    match: { level: "LOW", reason: "Python 일치" },
    recommendRank: 3,
    duties: ["서버 백엔드 개발", "API 설계와 테스트", "운영 이슈 확인과 기록"],
    requirements: ["Python 활용 (필수)"],
    matchedSkills: ["Python"],
    gapAdvice: "희망 직무와 다른 직종이에요. 서버 개발 경험이 있다면 사례로 정리해 보세요.",
    applyNote: "시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
];

export function getJobPosting(id: string): JobPosting | undefined {
  return jobPostings.find((job) => job.id === id);
}
