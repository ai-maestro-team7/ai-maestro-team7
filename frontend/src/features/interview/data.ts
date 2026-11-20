import type { AnswerGuideItem, InterviewModeOption, InterviewType } from "./types";

/** 설정 화면에 미리 채워 두는 값. 데모 직무는 데이터 분석, 자기소개서는 데이터 분석 가상 자소서다 (D-37, docs/api.md §6.2). */
export const interviewDefaults = {
  job: "데이터 분석",
  interviewType: "MIXED" as InterviewType,
  coverLetter:
    "부산 관광 공공데이터로 월별 방문객 추이를 분석했고, 결측치 처리 기준을 정해 회귀분석 결과를 검증했습니다. 발표 준비에서는 팀원과 역할을 나눠 결론을 정리했습니다.",
} as const;

export const MODE_OPTIONS: InterviewModeOption[] = [
  { value: "camera", label: "음성 + 카메라", badge: "추천", description: "내용, 전달력, 시선을 확인해요" },
  { value: "voice", label: "음성만", description: "내용과 전달력을 확인해요" },
  { value: "text", label: "텍스트", description: "답변 내용을 확인해요" },
];

export const TYPE_OPTIONS: { value: InterviewType; label: string }[] = [
  { value: "MIXED", label: "혼합" },
  { value: "PERSONALITY", label: "인성" },
  { value: "JOB", label: "직무" },
];

/** 면접 규칙 (docs/개발계획서3.md §5.6). 서버 규칙과 같은 값이다. */
export const RULES = {
  /** 기본 질문 수. 질문마다 꼬리질문이 최대 1개 붙는다 */
  baseQuestions: 3,
  /** 답변 제한 시간(초). 지나면 자동으로 제출한다 */
  answerLimitSec: 120,
  /** 남은 시간을 알리는 시점(초) */
  warnAtSec: [30, 10],
  /** `/status` 조회 간격(ms) */
  pollMs: 2000,
  /** 답변 중 캡처 간격(ms) */
  answerFrameMs: 2000,
  /** 정면 보정: 0.5초 간격으로 3초 */
  calibrationFrameMs: 500,
  calibrationFrames: 6,
  /** 정면 보정에 필요한 유효 캡처 수 */
  calibrationMinValid: 3,
  /** 답변을 낼 때 보내던 캡처를 기다리는 시간(ms) */
  frameFlushMs: 3000,
  resumeMin: 50,
  resumeMax: 5000,
  /** 채용공고 (C #158 settings.JOB_POSTING_*) */
  postingMin: 30,
  postingMax: 4000,
  postingTitleMax: 200,
  postingCompanyMax: 100,
  jobMax: 50,
  answerTextMax: 3000,
} as const;

export const answerGuide: AnswerGuideItem[] = [
  { title: "상황과 과제", description: "문제를 만난 상황과 본인의 역할을 먼저 설명해 보세요." },
  { title: "행동과 결과", description: "직접 한 행동과 검증한 결과를 구체적으로 써 보세요." },
];
