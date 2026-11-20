import type { Roadmap } from "./types";

/** 시연용 학습 로드맵 (Figma 학습 로드맵 화면 값) */
export const roadmap: Roadmap = {
  targetRole: "백엔드 개발자",
  basis: "진단에서 확인한 역량 격차 기준",
  order: ["배포 자동화", "로그·모니터링", "자격증 검토"],
  weeks: [
    {
      week: 1,
      title: "배포 파이프라인 만들기",
      description: "샘플 API에 자동 테스트를 연결하고, 테스트가 통과하면 배포되는 파이프라인을 구성해 보세요.",
      deliverable: "파이프라인 설정과 실행 기록",
      gap: "CI/CD 역량 보완",
    },
    {
      week: 2,
      title: "서비스 상태 모니터링하기",
      description: "응답 시간과 오류율을 기록하고 장애 시나리오를 재현해 원인 분석과 복구 절차를 정리해 보세요.",
      deliverable: "지표 화면과 장애 대응 기록",
      gap: "관측·장애 대응 연습",
    },
    {
      week: 3,
      title: "관련 자격증 검토하기",
      description: "SQLD를 학습 후보로 검토하고, 데이터 모델링과 SQL 문제 풀이로 부족한 개념을 확인해 보세요.",
      deliverable: "학습 체크리스트",
      gap: "DB 기초 역량 보강",
    },
  ],
};
