/**
 * B 정책 지갑 API 응답 (`/api/v1/opportunities/policies*`, 카멜 표기).
 * 기준: `ai/busan-opportunity/src/opportunity/models/api.py` `PolicyCard`, `PolicyWalletResponse`.
 */

/** 정책 자격 판정 (B `PolicyEligibilityStatus`) */
export type PolicyStatus = "ELIGIBLE" | "CHECK_NEEDED" | "NOT_ELIGIBLE" | "AFTER_EMPLOYMENT";

/** 정책 묶음 (B `PolicyBucket`) */
export type PolicyBucket = "OPEN_NOW" | "NEXT_CYCLE" | "AFTER_EMPLOYMENT" | "SETTLEMENT" | "CLOSED";

export type Selection = "AUTOMATIC" | "FIRST_COME" | "LOTTERY" | "REVIEW";

export type PolicyCard = {
  policyId: string;
  title: string;
  summary?: string;
  category?: string;
  stage: "PREPARE" | "EMPLOYED" | "SETTLE";
  bucket: PolicyBucket;
  eligibility: { status: PolicyStatus; reasons: string[]; manualChecks: string[] };
  benefit?: { text: string; period?: string };
  application: {
    applyStart?: string;
    applyEnd?: string;
    expected?: string;
    selection?: Selection;
    lastCompetition?: string;
  };
  url?: string;
  source: string;
  asOf?: string;
  /** 상세에서만 */
  checklist?: string[];
};

export type PolicyWalletResponse = {
  profileUsed?: { ageRange?: string; residence?: string; employment?: string; income?: string };
  buckets: Partial<Record<PolicyBucket, PolicyCard[]>>;
  dataAsOf?: string;
};

export type PolicyDetailResponse = {
  policy: PolicyCard;
  dataAsOf?: string;
};
