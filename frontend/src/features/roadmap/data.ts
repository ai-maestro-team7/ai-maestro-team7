import type { Roadmap } from "./types";

/**
 * 시연용 학습 로드맵. 틀은 Figma 학습 로드맵 화면이고, 내용은 직무 진단 Mock의 역량 격차
 * (데이터 시각화 보완 필요, 분석 결과 보고 증빙 보완)와 공고 우대 자격(ADsP)에 맞춘 예시다.
 */
export const roadmap: Roadmap = {
  targetRole: "데이터 분석",
  basis: "진단에서 확인한 역량 격차 기준",
  order: ["데이터 시각화", "분석 결과 보고", "자격증 검토"],
  weeks: [
    {
      week: 1,
      title: "분석 대시보드 만들기",
      description: "공공데이터로 핵심 지표를 정하고, Tableau나 Python으로 지표 변화를 보여주는 대시보드를 만들어 보세요.",
      deliverable: "대시보드 화면과 지표 정의",
      gap: "데이터 시각화 보완",
    },
    {
      week: 2,
      title: "분석 결과 보고서 쓰기",
      description: "분석 질문, 사용한 데이터, 방법, 결론을 한 장으로 정리하고 의사결정에 쓸 제안을 덧붙여 보세요.",
      deliverable: "분석 보고서 1편",
      gap: "보고·공유 근거 보강",
    },
    {
      week: 3,
      title: "관련 자격증 검토하기",
      description: "ADsP를 학습 후보로 검토하고, 데이터 이해와 분석 기획 영역 문제 풀이로 부족한 개념을 확인해 보세요.",
      deliverable: "학습 체크리스트",
      gap: "분석 기초 역량 보강",
    },
  ],
};
