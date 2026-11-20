import type { ReviewNextStep, ReviewSample } from "./types";

export const REVIEW_TARGET_ROLE = "백엔드 개발자";

const FACT_ONLY_NOTE =
  "원문과 이력서에 있는 사실만 썼어요. 성과 수치는 직접 확인할 수 있는 값이 있을 때 추가해 주세요.";

/**
 * 시연용 첨삭 예시. 자기소개서는 Figma 화면 값이고, 이력서는 같은 틀에 채운 예시다.
 * 개선 예시에는 원문·이력서에 없는 경험이나 수치를 넣지 않는다 (제품 원칙 5).
 */
export const reviewSamples: ReviewSample[] = [
  {
    kind: "COVER_LETTER",
    tabLabel: "자기소개서",
    original:
      "팀 프로젝트에서 백엔드 개발을 담당했습니다. 데이터베이스 성능을 개선했고 팀원들과 협력해 프로젝트를 마무리했습니다.",
    originalNote: "보완할 점 · 역할, 방법, 검증 기준을 구체적으로 적어 보세요.",
    improved:
      "지역 행사 서비스의 조회 API를 FastAPI로 구현했습니다. PostgreSQL 실행 계획에서 병목을 확인한 뒤 복합 인덱스를 추가하고, 동일한 데이터로 응답 시간을 비교했습니다.",
    improvedNote: FACT_ONLY_NOTE,
  },
  {
    kind: "RESUME",
    tabLabel: "이력서",
    original: "지역 행사 웹 서비스 개발 (백엔드 담당). DB 최적화, API 개발.",
    originalNote: "보완할 점 · 사용한 기술과 맡은 작업을 항목별로 나눠 적어 보세요.",
    improved:
      "지역 행사 웹 서비스 · 백엔드 담당. FastAPI로 행사 조회 API 구현, PostgreSQL 실행 계획 분석 후 복합 인덱스 추가.",
    improvedNote: FACT_ONLY_NOTE,
  },
];

export const reviewNextStep: ReviewNextStep = {
  title: "면접에 활용하기",
  description: "구현하면서 내린 기술 결정과 검증 방법을 면접 답변으로 정리해 보세요.",
};
