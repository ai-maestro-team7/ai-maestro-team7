"use client";

import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { useApi } from "@/lib/useApi";
import { fetchPolicies } from "../data";
import type { PolicyWalletResponse } from "../types";
import { PolicyTable, PolicyTableSkeleton } from "./PolicyTable";

const HOME_COUNT = 3;

/** 홈 "부산 청년 지원 정책": 지금 신청할 수 있는 정책 3개 */
export function OpenPolicies() {
  const username = useUsername();
  const [state, reload] = useApi<PolicyWalletResponse>(`${username}|home`, fetchPolicies);

  if (state.status === "loading") return <PolicyTableSkeleton rows={HOME_COUNT} />;
  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;
  return <PolicyTable policies={(state.data.buckets.OPEN_NOW ?? []).slice(0, HOME_COUNT)} />;
}
