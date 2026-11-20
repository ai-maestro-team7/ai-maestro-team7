import type { DiagnosisGuideItem, DiagnosisResult } from "./types";

/** 진단 입력 화면 기본값 (시연용 이력서 파일 이름, 목표 직무). 데모 직무는 데이터 분석이다 (D-37). */
export const diagnosisDefaults = {
  fileName: "김하늘_데이터분석_이력서.pdf",
  fileNote: "시연용 이력서예요",
  targetRole: "데이터 분석",
} as const;

export const diagnosisGuide: DiagnosisGuideItem[] = [
  { title: "보유 역량", description: "경력, 기술, 프로젝트에서 확인되는 역량" },
  { title: "직무 적합도", description: "목표 직무에 필요한 역량과 비교한 결과" },
  { title: "역량 격차", description: "부족한 역량과 증빙이 더 필요한 항목" },
];

/**
 * 시연용 진단 결과. 틀과 숫자는 Figma 직무 진단 결과 화면 값이고,
 * 요구 역량은 데모 직무(데이터 분석, NCS 빅데이터분석 20010105)에 맞춘 예시다.
 * 서류에서 찾지 못한 역량은 "부족"으로 단정하지 않고 확인되지 않았다고 쓴다 (제품 원칙 5).
 */
export const diagnosisResult: DiagnosisResult = {
  targetRole: "데이터 분석",
  headline: "SQL과 통계 분석 경험이 강점이에요",
  summary: "시각화와 분석 결과 보고 사례를 보강하면 공고 요구 역량에 더 가까워져요.",
  stats: [
    { label: "서류 적합도", value: 86, unit: "점" },
    { label: "충족", value: 2, unit: "개" },
    { label: "보완 필요", value: 1, unit: "개" },
    { label: "증빙 보완", value: 1, unit: "개" },
  ],
  statsNote: "예시 이력서를 데이터 분석 요건과 비교했어요. 합격 확률이 아니에요.",
  requirements: [
    { name: "SQL, 데이터 추출", status: "MET", evidence: "공공데이터 SQL 집계 프로젝트" },
    { name: "통계 분석, Python", status: "MET", evidence: "통계학 전공 · 회귀분석 과제" },
    { name: "데이터 시각화", status: "GAP", evidence: "이력서에서 확인되지 않았어요" },
    { name: "분석 결과 보고", status: "EVIDENCE", evidence: "경험은 있지만 근거가 더 필요해요" },
  ],
  nextAction: {
    title: "분석 과정을 보여줄 사례를 추가해 보세요",
    description: "분석 목적, 사용한 데이터, 결론과 본인 역할을 이력서에 담아 보세요.",
  },
};
