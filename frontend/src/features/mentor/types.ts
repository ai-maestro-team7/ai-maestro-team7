export type MentorRecommendation = {
  title: string;
  meta: string;
  actionLabel: string;
  href: string;
};

/** 시연용 AI 멘토 답변. 실제 Agent 응답이 아니다. */
export type MentorReply = {
  answer: string;
  /** 답변 아래 바로가기 카드. 보통 하나, 파일 첨부처럼 갈 곳이 여럿이면 여러 개 */
  recommendations?: MentorRecommendation[];
};

export type MentorExample = {
  /** Chip에 보이는 짧은 글 */
  label: string;
  /** 보낼 때 질문으로 쓰는 문장 */
  question: string;
  reply: MentorReply;
};

/** 보내기 전 입력칸에 붙어 있는 파일. 이름과 크기만 들고 있고 파일 내용은 읽지 않는다. */
export type MentorAttachment = {
  name: string;
  sizeBytes: number;
};

/** 대화에 남는 글 한 건. 붙인 파일은 이름만 남긴다 (내용은 어디에도 보관하지 않는다). */
export type MentorMessage =
  | { role: "user"; question: string; attachmentName?: string }
  | ({ role: "assistant" } & MentorReply);

/** 브라우저에 보관하는 대화 하나 */
export type MentorConversation = {
  id: string;
  /** 첫 질문을 줄인 글. 대화 목록에 보인다 */
  title: string;
  /** 마지막으로 글이 오간 시각 (epoch ms). 목록 순서와 오래된 대화 정리에 쓴다 */
  updatedAt: number;
  messages: MentorMessage[];
};

/** 홈 "이어서 하기" 항목 */
export type ContinueItem = {
  title: string;
  description: string;
  href: string;
};
