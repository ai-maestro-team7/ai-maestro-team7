export type MentorRecommendation = {
  title: string;
  meta: string;
  actionLabel: string;
  href: string;
};

/** 시연용 AI 멘토 답변. 실제 Agent 응답이 아니다. */
export type MentorReply = {
  answer: string;
  recommendation?: MentorRecommendation;
};

export type MentorExample = {
  /** Chip에 보이는 짧은 글 */
  label: string;
  /** 보낼 때 질문으로 쓰는 문장 */
  question: string;
  reply: MentorReply;
};

export type MentorTurn = {
  question: string;
  reply: MentorReply;
};

/** 홈 "이어서 하기" 항목 */
export type ContinueItem = {
  title: string;
  description: string;
  href: string;
};
