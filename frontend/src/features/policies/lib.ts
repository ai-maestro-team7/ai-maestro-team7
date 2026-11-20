import type { StatusTone } from "@/components/ui/StatusDot";
import { formatDate } from "@/lib/format";
import type { PolicyBucket, PolicyCard, PolicyStatus, Selection } from "./types";

/** 상태 문구. Figma에서 목록은 "자격 확인 필요", 상세 상자는 "조건 확인 필요"로 적혀 있다. */
export const POLICY_STATUS: Record<PolicyStatus, { label: string; detailLabel: string; tone: StatusTone }> = {
  CHECK_NEEDED: { label: "자격 확인 필요", detailLabel: "조건 확인 필요", tone: "orange" },
  ELIGIBLE: { label: "조건 충족", detailLabel: "조건 충족", tone: "green" },
  NOT_ELIGIBLE: { label: "조건 미충족", detailLabel: "조건 미충족", tone: "red" },
  AFTER_EMPLOYMENT: { label: "취업하면 대상", detailLabel: "취업하면 대상", tone: "blue" },
};

/** 정책 묶음 순서와 이름 (B 정책 지갑) */
export const POLICY_BUCKETS: { value: PolicyBucket; label: string }[] = [
  { value: "OPEN_NOW", label: "지금 신청 가능" },
  { value: "NEXT_CYCLE", label: "다음 모집" },
  { value: "AFTER_EMPLOYMENT", label: "취업 후" },
  { value: "SETTLEMENT", label: "주거·정착" },
  { value: "CLOSED", label: "모집 마감" },
];

export const SELECTION_LABELS: Record<Selection, string> = {
  AUTOMATIC: "자격이 맞으면 지원",
  FIRST_COME: "선착순",
  LOTTERY: "추첨",
  REVIEW: "심사",
};

/** 정적 내보내기라 정책 ID는 주소 쿼리로 넘긴다. */
export function policyDetailHref(policyId: string): string {
  return `/policies/detail/?id=${encodeURIComponent(policyId)}`;
}

/** 신청 기간 한 줄. 날짜가 없으면 다음 모집 예정 문구, 그것도 없으면 "일정 확인 필요". */
export function applyPeriod(application: PolicyCard["application"]): string {
  const { applyStart, applyEnd, expected } = application;
  if (applyStart && applyEnd) return `${formatDate(applyStart)} ~ ${formatDate(applyEnd)}`;
  if (applyEnd) return `${formatDate(applyEnd)}까지`;
  if (applyStart) return `${formatDate(applyStart)}부터`;
  return expected ?? "일정 확인 필요";
}

/** 표에 넣을 첫 줄. 원문은 줄머리 기호(①, ○, -)와 줄바꿈이 섞여 있다. */
export function firstLine(text?: string): string {
  if (!text) return "";
  const line = text
    .split(/\r?\n/)
    .map((part) => part.replace(/^[\s①-⑳○ㅇ•·\-*]+/, "").trim())
    .find(Boolean);
  return line ?? "";
}
