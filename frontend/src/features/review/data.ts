import type { ReviewNextStep, ReviewSample } from "./types";

/** 데모 직무 (D-37) */
export const REVIEW_TARGET_ROLE = "데이터 분석";

const FACT_ONLY_NOTE =
  "원문과 이력서에 있는 사실만 썼어요. 성과 수치는 직접 확인할 수 있는 값이 있을 때 추가해 주세요.";

/**
 * 시연용 첨삭 예시. 틀은 Figma AI 서류 첨삭 화면이고, 내용은 데모 직무(데이터 분석)에 맞춘 예시다.
 * 개선 예시에는 원문·이력서에 없는 경험이나 수치를 넣지 않는다 (제품 원칙 5).
 */
export const reviewSamples: ReviewSample[] = [
  {
    kind: "COVER_LETTER",
    tabLabel: "자기소개서",
    original:
      "팀 프로젝트에서 데이터 분석을 담당했습니다. 데이터를 정리해 의미 있는 결과를 찾았고 팀원들과 협력해 발표를 마무리했습니다.",
    originalNote: "보완할 점 · 사용한 데이터, 분석 방법, 검증 기준을 구체적으로 적어 보세요.",
    improved:
      "부산 관광 공공데이터로 월별 방문객 추이를 분석하는 팀 프로젝트에서 데이터 정제와 SQL 집계를 맡았습니다. 결측치 처리 기준을 정한 뒤 회귀분석 결과를 전년 같은 달 자료와 비교해 검증했습니다.",
    improvedNote: FACT_ONLY_NOTE,
  },
  {
    kind: "RESUME",
    tabLabel: "이력서",
    original: "관광 데이터 분석 프로젝트 (데이터 담당). 데이터 정리, 통계 분석.",
    originalNote: "보완할 점 · 사용한 도구와 맡은 작업을 항목별로 나눠 적어 보세요.",
    improved:
      "부산 관광 공공데이터 분석 프로젝트 · 데이터 정제와 집계 담당. SQL로 월별 방문객 집계, Python으로 결측치 처리와 회귀분석.",
    improvedNote: FACT_ONLY_NOTE,
  },
];

export const reviewNextStep: ReviewNextStep = {
  title: "면접에 활용하기",
  description: "분석하면서 내린 판단과 검증 방법을 면접 답변으로 정리해 보세요.",
};
