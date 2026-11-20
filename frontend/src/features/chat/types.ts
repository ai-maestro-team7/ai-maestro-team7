/** 채팅 Agent 응답 (`/api/v1/agent/chat`, docs/개발계획서4.md §7). */

/** CANCELLED: 사용자가 답을 만드는 중에 멈췄다 */
export type MessageStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";

/** B Agent 공고 (숫자 점수 없이 3단계 말로만) */
export type ChatPosting = {
  jobPostingId: string;
  title: string;
  organization: string;
  workRegion: string;
  isBusan: boolean;
  isCapitalArea: boolean;
  closesAt: string;
  deadline?: string;
  salary: string;
  /** 공공기관이면 "기관 직원 평균 연 9,118만 원 (2025년 결산 · 알리오 경영공시, 신입 초봉 아님)" */
  orgPay?: string;
  career?: string;
  matchLevel: string;
  eligibility?: string;
  badges: string[];
  facts: string[];
  busanAlternativesCount?: number;
  isSample?: boolean;
};

/** B Agent 정책 */
export type ChatPolicy = {
  policyId: string;
  title: string;
  bucket: string;
  status: string;
  reasons: string[];
  manualChecks: string[];
  benefit?: string;
  selection?: string;
  applyStart?: string;
  applyEnd?: string;
  expected?: string;
  source: string;
  asOf?: string;
  url?: string;
};

export type ChatCard =
  | { type: "POSTING"; posting: ChatPosting }
  | { type: "POLICY"; policy: ChatPolicy };

/** "이 공고로" 면접할 때 Agent가 실어 주는 공고 (#167). 면접 화면은 이 공고로 질문을 만들고 공고 올리기를 끈다 */
export type LinkedPosting = { jobPostingId?: string; postingTitle?: string; postingOrganization?: string };

export type ChatAction =
  | { type: "SAVE_CONDITIONS"; conditions: string[]; profilePatch: Record<string, unknown> }
  | { type: "SUGGEST_INTERVIEW"; job: string }
  | ({ type: "START_INTERVIEW"; job: string; documentId: string; title?: string } & LinkedPosting)
  | ({ type: "REQUEST_COVER_LETTER"; job: string; minChars: number; maxChars: number } & LinkedPosting)
  /** 사용자가 채팅으로 저장을 승낙해 Agent가 저장했다 (D-40) */
  | { type: "CONDITIONS_SAVED"; conditions: string[] }
  | { type: "REVIEW_RESUME"; documentId: string };

export type ChatError = { code: string; message: string; retryable: boolean };

export type ChatMessage = {
  messageId: string;
  role: "USER" | "ASSISTANT";
  status: MessageStatus;
  /** 사용자 말 */
  content?: string;
  /** Agent 답 */
  reply?: string;
  followUps?: string[];
  cards?: ChatCard[];
  actions?: ChatAction[];
  attachments?: { documentId: string }[];
  notice?: string;
  dataAsOf?: string;
  error?: ChatError;
  createdAt?: string;
};

export type StartResponse = { sessionId: string; messageId: string; userMessageId: string; status: MessageStatus };

/** 대화 목록 한 줄 (`GET /api/v1/agent/chat`). 고정한 대화가 먼저, 그 안과 밖은 최근에 말한 순서로 온다 */
export type ChatSessionSummary = {
  sessionId: string;
  title: string;
  pinned: boolean;
  messageCount: number;
  createdAt: string;
  lastMessageAt: string;
  /** 답을 만드는 중이면 그 답의 ID */
  pendingMessageId?: string;
};

export type ChatSessionView = ChatSessionSummary & { messages: ChatMessage[] };

/** 채팅 → 면접 화면 인계 (sessionStorage, 개발계획서4 §10). 자소서 원문은 주소에 넣지 않는다. */
export type InterviewHandoff = {
  job: string;
  coverLetter?: string;
  documentId?: string;
  documentTitle?: string;
  /** 면접에 쓸 공고의 제목·기관. 공고 ID는 주소(?posting=)로 넘긴다 */
  posting?: { jobPostingId: string; title?: string; organization?: string };
  source: "chat";
  /** 남긴 사용자 (토큰 sub). 지금 로그인한 사용자와 다르면 쓰지 않는다 */
  owner: string | null;
};
