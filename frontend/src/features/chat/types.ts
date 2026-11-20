/** 채팅 Agent 응답 (`/api/v1/agent/chat`, docs/개발계획서4.md §7). */

export type MessageStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

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

export type ChatAction =
  | { type: "SAVE_CONDITIONS"; conditions: string[]; profilePatch: Record<string, unknown> }
  | { type: "SUGGEST_INTERVIEW"; job: string }
  | { type: "START_INTERVIEW"; job: string; documentId: string; title?: string }
  | { type: "REQUEST_COVER_LETTER"; job: string; minChars: number; maxChars: number }
  /** 사용자가 채팅으로 저장을 승낙해 Agent가 저장했다 (D-40) */
  | { type: "CONDITIONS_SAVED"; conditions: string[] };

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

export type ChatSessionView = { sessionId: string; title: string; messages: ChatMessage[] };

/** 채팅 → 면접 화면 인계 (sessionStorage, 개발계획서4 §10). 자소서 원문은 주소에 넣지 않는다. */
export type InterviewHandoff = {
  job: string;
  coverLetter?: string;
  documentId?: string;
  documentTitle?: string;
  source: "chat";
  /** 남긴 사용자 (토큰 sub). 지금 로그인한 사용자와 다르면 쓰지 않는다 */
  owner: string | null;
};
