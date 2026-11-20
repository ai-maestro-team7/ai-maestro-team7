import type { JobPosting } from "./types";

/** Mock 데이터 기준일. D-day 계산과 "기준" 표시에 쓴다. */
export const DATA_AS_OF = "2026-11-20";

/** 추천 기준 프로필 표시 (공고 목록 상단) */
export const RECOMMEND_BASIS = {
  role: "백엔드 개발",
  skills: ["Python", "REST API", "PostgreSQL"],
} as const;

/**
 * 시연용 예시 공고. 기업·공고는 모두 가상이다.
 * 첫 공고는 Figma 화면 값 그대로이고, 나머지 상세 내용은 같은 틀에 채운 예시다.
 */
export const jobPostings: JobPosting[] = [
  {
    id: "centum-backend",
    company: "센텀테크",
    companyInitial: "센",
    companyNote: "시연용 예시 기업",
    title: "백엔드 개발자",
    skills: ["Python", "REST API"],
    district: "해운대구",
    employmentType: "정규직",
    careerLevel: "신입",
    deadline: "2026-12-05",
    match: { level: "GOOD", reason: "Python, REST API 일치" },
    recommendRank: 1,
    duties: ["서비스 REST API 설계와 개발", "PostgreSQL 데이터 모델링과 운영", "배포 자동화와 서비스 모니터링"],
    requirements: ["Python 기반 웹 개발 경험", "SQL 활용 경험", "Git 협업 경험"],
    matchedSkills: ["Python", "REST API", "PostgreSQL"],
    gapAdvice: "배포 자동화 경험을 포트폴리오에 추가해 보세요.",
    applyNote: "시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
  {
    id: "yeongdo-data-platform",
    company: "영도데이터",
    companyInitial: "영",
    companyNote: "시연용 예시 기업",
    title: "데이터 플랫폼 개발자",
    skills: ["SQL", "ETL"],
    district: "영도구",
    employmentType: "계약직",
    careerLevel: "신입",
    deadline: "2026-12-12",
    match: { level: "FAIR", reason: "SQL 일치" },
    recommendRank: 2,
    duties: ["데이터 수집·적재(ETL) 파이프라인 개발", "SQL 기반 데이터 마트 설계", "데이터 품질 점검 자동화"],
    requirements: ["SQL 활용 경험", "ETL 스크립트 작성 경험", "Python 또는 Java 기초"],
    matchedSkills: ["SQL", "PostgreSQL"],
    gapAdvice: "ETL 파이프라인을 직접 만든 사례를 정리해 보세요.",
    applyNote: "시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
  {
    id: "dongbaek-server-intern",
    company: "동백소프트",
    companyInitial: "동",
    companyNote: "시연용 예시 기업",
    title: "서버 개발 인턴",
    skills: ["Java", "Spring Boot"],
    district: "부산진구",
    employmentType: "인턴",
    careerLevel: "신입",
    deadline: null,
    match: { level: "FAIR", reason: "백엔드 직무 일치" },
    recommendRank: 3,
    duties: ["Spring Boot 기반 API 개발 보조", "테스트 코드 작성", "운영 이슈 확인과 기록"],
    requirements: ["Java 기초 문법", "웹 서비스 구조 이해", "Git 사용 경험"],
    matchedSkills: ["REST API", "Git"],
    gapAdvice: "Java·Spring Boot 학습 이력을 이력서에 보강해 보세요.",
    applyNote: "시연용 공고라 실제 지원 페이지와는 연결되어 있지 않아요.",
  },
];

export function getJobPosting(id: string): JobPosting | undefined {
  return jobPostings.find((job) => job.id === id);
}
