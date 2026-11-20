import type { StatusTone } from "@/components/ui/StatusDot";
import type { PolicyStatus } from "./types";

/** 상태 문구. Figma에서 목록은 "자격 확인 필요", 상세 상자는 "조건 확인 필요"로 적혀 있다. */
export const POLICY_STATUS: Record<PolicyStatus, { label: string; detailLabel: string; tone: StatusTone }> = {
  CHECK_NEEDED: { label: "자격 확인 필요", detailLabel: "조건 확인 필요", tone: "orange" },
  ELIGIBLE: { label: "조건 충족", detailLabel: "조건 충족", tone: "green" },
  NOT_ELIGIBLE: { label: "조건 미충족", detailLabel: "조건 미충족", tone: "red" },
};
