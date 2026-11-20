/** 진행 방식: 음성 + 카메라 / 음성만 / 텍스트 */
export type InterviewMode = "camera" | "voice" | "text";

export type InterviewModeOption = {
  value: InterviewMode;
  label: string;
  badge?: string;
  description: string;
};

/** 면접 유형 (`POST /interview/start`의 `interviewType`) */
export type InterviewType = "PERSONALITY" | "JOB" | "MIXED";

export type AnswerGuideItem = { title: string; description: string };

// ---------------------------------------------------------------- API (docs/개발계획서3.md §5)

export type InterviewStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export type InterviewStage =
  | "QUESTION_GENERATING"
  | "NEXT_QUESTION_READY"
  | "TRANSCRIBING"
  | "JUDGING"
  | "REPORT_GENERATING"
  | "REPORT_READY";

/** 지금 답할 질문. `answerId`는 답변과 캡처를 보낼 때 그대로 돌려준다. */
export type NextQuestion = {
  questionId: string;
  answerId: string;
  text: string;
  isFollowUp: boolean;
  /** 질문 음성 (S3 임시 주소, 10분). 음성을 만들지 못했으면 null */
  audioUrl: string | null;
};

export type UnevaluableReason = "NO_ANSWER" | "TRANSCRIBE_FAILED";

export type LastAnswer = { answerId: string; evaluable: boolean; reason: UnevaluableReason | null };

export type AreaScore = { score: number | null; notMeasuredReason: string | null };

export type ReportQuestion = {
  questionId: string;
  question: string;
  followUp: { question: string; answerText: string | null } | null;
  answerText: string | null;
  evaluable: boolean;
  reason?: UnevaluableReason | null;
  contentScore: number | null;
  strengths: string[];
  improvements: string[];
  direction: string | null;
  metrics: {
    /** 분당 음절 수 */
    speechRate: number | null;
    longPausePerMin: number | null;
    /** 정면 응시 비율(%) */
    frontalRatio: number | null;
    timeLimitReached: boolean;
  };
  comment: string | null;
};

export type InterviewReport = {
  interviewDate?: string;
  job: string;
  interviewType: InterviewType;
  evaluatedBaseQuestions: number;
  totalScore: number | null;
  grade: string | null;
  weightBasis: string;
  areas: { content: AreaScore; delivery: AreaScore; attitude: AreaScore };
  notMeasuredMessages: string[];
  questions: ReportQuestion[];
  notice: string;
};

export type InterviewError = { code: string; message: string; requestId?: string; retryable?: boolean };

/** `GET /interview/{sessionId}/status` */
export type InterviewStatusBody = {
  sessionId: string;
  status: InterviewStatus;
  stage: InterviewStage;
  progress: { baseQuestionNo: number; totalBaseQuestions: number; isFollowUp: boolean };
  nextQuestion: NextQuestion | null;
  lastAnswer: LastAnswer | null;
  report: InterviewReport | null;
  error?: InterviewError | null;
};

/** 면접 시작 입력. 서류는 직접 쓴 글(`resumeText`)이나 올린 문서(`documentId`, A 문서) 가운데 하나를 보낸다. */
export type StartInterviewInput = {
  job: string;
  resumeText?: string;
  documentId?: string;
  interviewType: InterviewType;
  cameraConsent: boolean;
};
