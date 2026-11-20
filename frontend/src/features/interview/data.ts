import type {
  AnswerGuideItem,
  DeviceCheckItem,
  InterviewModeOption,
  InterviewQuestion,
  InterviewReport,
} from "./types";

/** 데모 직무는 데이터 분석, 자기소개서는 데이터 분석 가상 자소서다 (D-37, docs/api.md §6.2). */
export const interviewDefaults = {
  job: "데이터 분석",
  interviewType: "혼합 면접",
  coverLetter:
    "부산 관광 공공데이터로 월별 방문객 추이를 분석했고, 결측치 처리 기준을 정해 회귀분석 결과를 검증했습니다. 발표 준비에서는 팀원과 역할을 나눠 결론을 정리했습니다.",
} as const;

export const MODE_OPTIONS: InterviewModeOption[] = [
  { value: "camera", label: "음성 + 카메라", badge: "추천", description: "내용, 전달력, 시선을 확인해요" },
  { value: "voice", label: "음성만", description: "내용과 전달력을 확인해요" },
  { value: "text", label: "텍스트", description: "답변 내용을 확인해요" },
];

/**
 * 시연용 면접 질문 3개와 질문별 추가 질문 1개 (C §1: 기본 질문 3개, 문항당 꼬리질문 최대 1개).
 * 틀은 Figma 면접 화면이고, 내용은 위 자기소개서에서 나올 만한 질문으로 채운 예시다.
 */
export const interviewQuestions: InterviewQuestion[] = [
  {
    id: "q1",
    topic: "데이터 분석 프로젝트",
    question: "팀 프로젝트에서 데이터를 분석해 문제를 해결한 경험을 설명해 주세요.",
    hint: "어떤 데이터를 썼고, 분석 결과는 어떻게 검증했나요?",
    sampleAnswer:
      "부산 관광 공공데이터에서 월별 방문객을 SQL로 집계했습니다. 결측치 처리 기준을 정하고 회귀분석 결과를 전년 같은 달 자료와 비교했습니다.",
    followUp: {
      question: "결측치 처리 기준은 어떤 근거로 정했나요?",
      hint: "다른 방법과 비교했는지, 결과에 어떤 차이가 있었는지 설명해 주세요.",
      sampleAnswer:
        "결측 비율이 낮은 항목은 같은 달 평균으로 채우고, 높은 항목은 분석에서 뺀 뒤 두 방식의 결과 차이를 비교했습니다.",
      reason: "앞 답변에서 결측치 처리 기준을 언급했어요. 어떤 근거와 비교로 정했는지 구체적으로 답해 보세요.",
    },
  },
  {
    id: "q2",
    topic: "협업 중 의견 조율",
    question: "팀원과 분석 방법에서 의견이 달랐던 경험을 말해 주세요.",
    hint: "의견 차이를 어떻게 좁혔고, 최종 결정은 어떻게 내렸나요?",
    sampleAnswer:
      "방문객 지표 정의를 두고 의견이 갈려 두 지표로 같은 기간을 계산해 비교하자고 제안했습니다. 결과를 공유한 뒤 함께 하나로 정했습니다.",
    followUp: {
      question: "두 지표를 비교한 뒤 무엇을 기준으로 하나를 골랐나요?",
      hint: "결정 기준과 그 결정이 팀 작업에 미친 효과를 설명해 주세요.",
      sampleAnswer: "분석 질문에 더 직접 답하는지와 데이터 누락이 적은지를 기준으로 정리해 팀 회의에서 정했습니다.",
      reason: "앞 답변에서 작은 비교 실험을 제안했다고 했어요. 결정 기준과 결과를 구체적으로 답해 보세요.",
    },
  },
  {
    id: "q3",
    topic: "분석 결과 전달",
    question: "분석 결과를 데이터를 잘 모르는 사람에게 설명한 경험이 있나요?",
    hint: "어떤 순서로 설명했고, 상대가 이해했는지는 어떻게 확인했나요?",
    sampleAnswer:
      "발표에서 결론을 먼저 말하고 근거 그래프 두 개만 보여 줬습니다. 질문을 받아 이해가 부족한 부분을 다시 설명했습니다.",
    followUp: {
      question: "결론을 뒷받침하려고 어떤 수치를 골랐나요?",
      hint: "여러 수치 중 그 값을 고른 이유를 설명해 주세요.",
      sampleAnswer: "전년 같은 달 대비 변화율을 골랐습니다. 계절 영향을 줄여 비교할 수 있어서였습니다.",
      reason: "앞 답변에서 결론을 먼저 말했다고 했어요. 근거로 고른 수치와 이유를 구체적으로 답해 보세요.",
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

/** 시연용 리포트. 점수·말하기 시간·정면 응시 값은 Figma 모의면접 · 리포트 화면 값이고, 피드백은 위 질문에 맞춘 예시다. */
export const interviewReport: InterviewReport = {
  summary: "데이터 분석 · 혼합 면접 · 음성 + 카메라 · 결과 예시",
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
      topic: "데이터 분석 프로젝트",
      comment: "결측치 처리와 검증 과정을 구체적으로 설명했어요. 분석 결과가 어떤 결정에 쓰였는지 덧붙여 보세요.",
      speakingSeconds: 64,
      frontGazeRate: 81,
      gazeNeedsAttention: false,
    },
    {
      id: "q2",
      label: "Q2",
      topic: "협업 중 의견 조율",
      comment: "작은 비교 실험을 제안한 판단이 좋았어요. 결정 이후 팀에 미친 효과도 설명해 보세요.",
      speakingSeconds: 78,
      frontGazeRate: 69,
      gazeNeedsAttention: true,
    },
    {
      id: "q3",
      label: "Q3",
      topic: "분석 결과 전달",
      comment: "결론을 먼저 말한 순서가 좋았어요. 결론을 뒷받침한 수치를 하나 덧붙여 보세요.",
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
