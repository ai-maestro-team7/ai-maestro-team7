"use client";

import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { useApi } from "@/lib/useApi";
import { fetchPolicies } from "../data";
import type { PolicyWalletResponse } from "../types";
import { PolicyTable, PolicyTableSkeleton } from "./PolicyTable";

const HOME_COUNT = 3;

/** 홈 "지금 신청할 수 있는 청년 정책": 내 기본 정보로 지금 신청할 수 있는 정책 3개 (부산·전국) */
export function OpenPolicies() {
  const username = useUsername();
  const [state, reload] = useApi<PolicyWalletResponse>(`${username}|home`, fetchPolicies);

  if (state.status === "loading") return <PolicyTableSkeleton rows={HOME_COUNT} />;
  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;
  return <PolicyTable policies={(state.data.buckets.OPEN_NOW ?? []).slice(0, HOME_COUNT)} />;
}
