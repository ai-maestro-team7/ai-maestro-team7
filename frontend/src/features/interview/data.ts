import type { AnswerGuideItem, InterviewModeOption, InterviewType } from "./types";

/**
 * 면접 기본값. 설정 화면의 직무와 자기소개서는 빈칸으로 시작하고 입력칸 안내 글로 쓰는 법만 보여 준다.
 * `job`은 장비 점검·면접·리포트 주소에 직무가 빠졌을 때만 쓴다 (설정 화면에서 넘어오면 늘 들어 있다).
 */
export const interviewDefaults = {
  job: "데이터 분석",
  interviewType: "MIXED" as InterviewType,
} as const;

/** 입력칸 안내 글 (흐린 글씨). 예시는 쓰는 법을 보여 주려는 것이고 값으로 들어가지 않는다 */
export const SETUP_PLACEHOLDERS = {
  job: "예: 데이터 분석, 백엔드 개발, 마케팅",
  coverLetter:
    "어떤 경험에서 무엇을 했고 결과가 어땠는지 순서대로 써 주세요. 50자 이상이면 돼요.\n예: 공공데이터로 월별 방문객 추이를 분석했고, 결측치 기준을 정해 회귀분석 결과를 검증했어요. 발표에서는 팀원과 역할을 나눠 결론을 정리했어요.",
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
