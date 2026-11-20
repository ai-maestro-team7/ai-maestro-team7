export type ReviewDocumentKind = "COVER_LETTER" | "RESUME";

export type ReviewSample = {
  kind: ReviewDocumentKind;
  tabLabel: string;
  original: string;
  /** 원문 아래 "보완할 점" */
  originalNote: string;
  improved: string;
  /** 개선 예시 아래 사실 확인 안내 */
  improvedNote: string;
};

export type ReviewNextStep = { title: string; description: string };
