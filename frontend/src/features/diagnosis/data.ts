import type { DiagnosisGuideItem, DiagnosisResult } from "./types";

/** 진단 입력 화면 기본값 (시연용 이력서 파일 이름, 목표 직무) */
export const diagnosisDefaults = {
  fileName: "김하늘_백엔드_이력서.pdf",
  fileNote: "시연용 이력서예요",
  targetRole: "백엔드 개발자",
} as const;

export const diagnosisGuide: DiagnosisGuideItem[] = [
  { title: "보유 역량", description: "경력, 기술, 프로젝트에서 확인되는 역량" },
  { title: "직무 적합도", description: "목표 직무에 필요한 역량과 비교한 결과" },
  { title: "역량 격차", description: "부족한 역량과 증빙이 더 필요한 항목" },
];

/** 시연용 진단 결과 (Figma 직무 진단 결과 화면 값) */
export const diagnosisResult: DiagnosisResult = {
  targetRole: "백엔드 개발자",
  headline: "Python과 API 설계 경험이 강점이에요",
  summary: "배포 자동화와 서비스 관측 사례를 보강하면 공고 요구 역량에 더 가까워져요.",
  stats: [
    { label: "서류 적합도", value: 86, unit: "점" },
    { label: "충족", value: 2, unit: "개" },
    { label: "보완 필요", value: 1, unit: "개" },
    { label: "증빙 보완", value: 1, unit: "개" },
  ],
  statsNote: "예시 이력서를 백엔드 개발자 요건과 비교했어요. 합격 확률이 아니에요.",
  requirements: [
    { name: "Python, FastAPI", status: "MET", evidence: "지역 행사 API 구현 경험" },
    { name: "SQL, 데이터 모델링", status: "MET", evidence: "PostgreSQL 인덱스 개선 경험" },
    { name: "CI/CD, 배포 자동화", status: "GAP", evidence: "이력서에서 확인되지 않았어요" },
    { name: "모니터링, 로그 추적", status: "EVIDENCE", evidence: "경험은 있지만 근거가 더 필요해요" },
  ],
  nextAction: {
    title: "역량을 보여줄 사례를 추가해 보세요",
    description: "API 성능 개선 전후 수치와 본인 역할을 이력서에 담아 보세요.",
  },
};
