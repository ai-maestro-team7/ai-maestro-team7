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

/** 질문에 붙인 파일. 대화에는 이름과 크기만 남긴다 (파일 내용은 보관하지 않는다). */
export type MentorAttachment = {
  name: string;
  sizeBytes: number;
};

export type MentorTurn = {
  question: string;
  attachment?: MentorAttachment;
  reply: MentorReply;
};

/** 홈 "이어서 하기" 항목 */
export type ContinueItem = {
  title: string;
  description: string;
  href: string;
};
