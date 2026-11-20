import type { StatItem } from "@/components/ui/Stats";

/** 진행 방식: 음성 + 카메라 / 음성만 / 텍스트 */
export type InterviewMode = "camera" | "voice" | "text";

export type InterviewModeOption = {
  value: InterviewMode;
  label: string;
  badge?: string;
  description: string;
};

export type FollowUpQuestion = {
  question: string;
  hint: string;
  sampleAnswer: string;
  /** "왜 이 질문인가요?" 설명 */
  reason: string;
};

export type InterviewQuestion = {
  id: string;
  topic: string;
  question: string;
  hint: string;
  /** 텍스트 방식에서 입력칸에 미리 채우는 예시 답변 */
  sampleAnswer: string;
  /** 질문당 추가 질문은 최대 1개 (C §1) */
  followUp: FollowUpQuestion;
};

export type DeviceCheckItem = {
  key: "mic" | "camera" | "questions";
  title: string;
  description: string;
};

export type AnswerGuideItem = { title: string; description: string };

export type QuestionFeedback = {
  id: string;
  label: string;
  topic: string;
  comment: string;
  speakingSeconds: number;
  frontGazeRate: number;
  /** 정면 응시 비율을 주의 색으로 보여줄지 */
  gazeNeedsAttention: boolean;
};

export type InterviewReport = {
  summary: string;
  stats: StatItem[];
  statsNote: string;
  feedback: QuestionFeedback[];
  next: { title: string; description: string };
};
