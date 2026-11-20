import type {
  AnswerGuideItem,
  DeviceCheckItem,
  InterviewModeOption,
  InterviewQuestion,
  InterviewReport,
} from "./types";

export const interviewDefaults = {
  job: "백엔드 개발자",
  interviewType: "혼합 면접",
  coverLetter:
    "FastAPI로 지역 행사 API를 구현했고, PostgreSQL 인덱스를 개선해 조회 속도를 줄였습니다. 배포 과정에서는 팀원과 역할을 나눠 장애 원인을 추적했습니다.",
} as const;

export const MODE_OPTIONS: InterviewModeOption[] = [
  { value: "camera", label: "음성 + 카메라", badge: "추천", description: "내용, 전달력, 시선을 확인해요" },
  { value: "voice", label: "음성만", description: "내용과 전달력을 확인해요" },
  { value: "text", label: "텍스트", description: "답변 내용을 확인해요" },
];

/**
 * 시연용 면접 질문. 1번 질문과 추가 질문은 Figma 화면 값이고,
 * 2·3번은 리포트의 질문별 피드백 주제에 맞춰 채운 예시다.
 */
export const interviewQuestions: InterviewQuestion[] = [
  {
    id: "q1",
    topic: "API 성능 개선",
    question: "팀 프로젝트에서 API 응답 속도를 개선한 경험을 설명해 주세요.",
    hint: "어떤 병목을 찾았고, 개선 효과는 어떻게 검증했나요?",
    sampleAnswer:
      "지역 행사 조회 API에서 실행 계획을 확인했습니다. 복합 인덱스를 추가하고 같은 데이터로 개선 전후 응답 시간을 비교했습니다.",
    followUp: {
      question: "인덱스를 추가하기 전후의 응답 시간은 어떤 조건에서 비교했나요?",
      hint: "같은 데이터로 비교했는지, 어떤 지표로 효과를 확인했는지 설명해 주세요.",
      sampleAnswer: "동일한 데이터에서 같은 쿼리를 반복 실행하고 평균 응답 시간과 실행 계획을 비교했습니다.",
      reason: "앞 답변에서 전후 비교를 언급했어요. 어떤 조건과 수치로 검증했는지 구체적으로 답해 보세요.",
    },
  },
  {
    id: "q2",
    topic: "협업 중 의견 조율",
    question: "팀원과 기술 선택에서 의견이 달랐던 경험을 말해 주세요.",
    hint: "의견 차이를 어떻게 좁혔고, 최종 결정은 어떻게 내렸나요?",
    sampleAnswer:
      "캐시 도입 여부로 의견이 갈려 작은 실험을 제안했습니다. 같은 요청으로 두 방식을 비교한 결과를 공유하고 함께 결정했습니다.",
    followUp: {
      question: "실험 결과를 팀에 공유한 뒤 결정은 어떻게 내렸나요?",
      hint: "결정 기준과 그 결정이 팀에 미친 효과를 설명해 주세요.",
      sampleAnswer: "응답 시간과 운영 부담을 기준으로 정리해 공유했고, 팀 회의에서 함께 결정했습니다.",
      reason: "앞 답변에서 작은 실험을 제안했다고 했어요. 결정 기준과 결과를 구체적으로 답해 보세요.",
    },
  },
  {
    id: "q3",
    topic: "배포 장애 대응",
    question: "배포 후 장애가 났을 때 어떻게 대응했는지 설명해 주세요.",
    hint: "영향 범위를 어떻게 확인했고, 복구는 어떻게 판단했나요?",
    sampleAnswer:
      "오류 로그로 영향 범위를 먼저 확인하고 직전 버전으로 롤백했습니다. 이후 원인을 팀원과 나눠 추적했습니다.",
    followUp: {
      question: "롤백을 결정한 기준은 무엇이었나요?",
      hint: "복구 여부를 판단할 때 본 지표를 설명해 주세요.",
      sampleAnswer: "오류율이 평소보다 높게 유지되는지와 주요 API 응답 여부를 보고 판단했습니다.",
      reason: "앞 답변에서 롤백을 언급했어요. 어떤 지표로 판단했는지 구체적으로 답해 보세요.",
    },
  },
];

export const deviceChecks: Record<DeviceCheckItem["key"], DeviceCheckItem> = {
  mic: { key: "mic", title: "마이크", description: "입력 레벨이 적당해요" },
  camera: { key: "camera", title: "카메라", description: "분석에 동의했고 얼굴이 가운데 있어요" },
  questions: { key: "questions", title: "질문", description: "질문이 준비됐어요" },
};

export const answerGuide: AnswerGuideItem[] = [
  { title: "상황과 과제", description: "문제를 만난 상황과 본인의 역할을 먼저 설명해 보세요." },
  { title: "행동과 결과", description: "직접 한 행동과 검증한 결과를 구체적으로 써 보세요." },
];

/** 녹음 파형 막대 높이(px). Figma Waveform 값 그대로. 앞 30개는 말한 구간(파란색). */
export const WAVEFORM_BARS = [
  10, 20, 32, 18, 26, 40, 24, 14, 34, 22, 28, 16, 38, 20, 26, 12, 32, 20, 30, 18, 40, 24, 14, 26, 20, 34, 22, 12, 28,
  16, 36, 20, 26, 14, 32, 20, 10, 24, 18, 10, 22, 14, 28, 18, 12, 24, 16, 10,
];
export const WAVEFORM_SPOKEN = 30;

/** 시연용 리포트 (Figma 모의면접 · 리포트 화면 값) */
export const interviewReport: InterviewReport = {
  summary: "백엔드 개발자 · 혼합 면접 · 음성 + 카메라 · 결과 예시",
  stats: [
    { label: "종합", value: 82, unit: "점" },
    { label: "내용", value: 88, unit: "점" },
    { label: "전달력", value: 81, unit: "점" },
    { label: "시선·자세", value: 77, unit: "점" },
  ],
  statsNote: "면접 점수는 연습용 지표예요. 합격 확률이 아니에요.",
  feedback: [
    {
      id: "q1",
      label: "Q1",
      topic: "API 성능 개선",
      comment: "인덱스 개선 과정을 구체적으로 설명했어요. 전후 응답 시간과 측정 조건을 덧붙여 보세요.",
      speakingSeconds: 64,
      frontGazeRate: 81,
      gazeNeedsAttention: false,
    },
    {
      id: "q2",
      label: "Q2",
      topic: "협업 중 의견 조율",
      comment: "작은 실험을 제안한 판단이 좋았어요. 결정 이후 팀에 미친 효과도 설명해 보세요.",
      speakingSeconds: 78,
      frontGazeRate: 69,
      gazeNeedsAttention: true,
    },
    {
      id: "q3",
      label: "Q3",
      topic: "배포 장애 대응",
      comment: "영향 범위 확인과 롤백을 언급했어요. 복구를 판단할 기준 지표를 추가해 보세요.",
      speakingSeconds: 51,
      frontGazeRate: 82,
      gazeNeedsAttention: false,
    },
  ],
  next: {
    title: "2번 질문에서 시선이 자주 벗어났어요",
    description: "답변의 핵심을 말할 때 카메라 가까이를 바라보는 연습을 해 보세요.",
  },
};
