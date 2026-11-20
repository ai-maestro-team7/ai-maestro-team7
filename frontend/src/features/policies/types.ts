/** 정책 자격 상태. 지금 Mock은 모두 "확인 필요"다 (B 정책 CHECK_NEEDED). */
export type PolicyStatus = "CHECK_NEEDED" | "ELIGIBLE" | "NOT_ELIGIBLE";

export type PolicyChecklistItem = {
  title: string;
  description: string;
};

export type Policy = {
  id: string;
  name: string;
  /** 지원 내용 (표) */
  benefit: string;
  /** 추천 대상 (표) */
  target: string;
  /** 확인할 조건 (표) */
  conditions: string;
  status: PolicyStatus;
  /** 상세 제목 아래 한 줄 설명 */
  summary: string;
  checklist: PolicyChecklistItem[];
  reason: string;
  officialSource: { label: string; url: string };
  note: string;
};
