import { apiGet } from "@/lib/api";
import type { PolicyDetailResponse, PolicyWalletResponse } from "./types";

/** 정책 데이터는 B API에서 읽는다 (개발계획서2 B-08 정책 지갑). */
const BASE = "/api/v1/opportunities";

/** 내 기본 프로필로 판정한 정책 묶음 */
export function fetchPolicies(): Promise<PolicyWalletResponse> {
  return apiGet<PolicyWalletResponse>(`${BASE}/policies`);
}

export function fetchPolicy(policyId: string): Promise<PolicyDetailResponse> {
  return apiGet<PolicyDetailResponse>(`${BASE}/policies/${encodeURIComponent(policyId)}`);
}

/** 신청 전 공식 확인처 (목록 아래 안내 상자) */
export const BUSAN_YOUTH_PLATFORM = { label: "부산청년플랫폼", url: "https://young.busan.go.kr" } as const;
