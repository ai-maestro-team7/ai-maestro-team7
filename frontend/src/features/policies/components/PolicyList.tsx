"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ApiErrorNotice, ApiLoading } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { fetchPolicies } from "../data";
import { POLICY_BUCKETS } from "../lib";
import type { PolicyBucket, PolicyWalletResponse } from "../types";
import { PolicyTable } from "./PolicyTable";

/** 한 번에 보여주는 정책 수. 정책은 한 번에 다 받아 오고 화면에서만 나눠 보여준다. */
const PAGE = 20;

/** 청년 지원 정책 목록 (B-08 정책 지갑): 묶음 고르기, 더 보기. */
export function PolicyList() {
  const username = useUsername();
  const [state, reload] = useApi<PolicyWalletResponse>(`${username}`, fetchPolicies);
  const [bucket, setBucket] = useState<PolicyBucket>("OPEN_NOW");
  const [shown, setShown] = useState(PAGE);

  if (state.status === "loading") return <ApiLoading className="py-24" label="정책을 불러오는 중" />;
  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;

  const wallet = state.data;
  const items = wallet.buckets[bucket] ?? [];
  const profile = wallet.profileUsed;
  const profileText = [profile?.ageRange && `${profile.ageRange}세`, profile?.residence].filter(Boolean).join(" · ");

  return (
    <div className="flex w-full flex-col gap-5">
      <div role="group" aria-label="정책 묶음" className="flex flex-wrap gap-2">
        {POLICY_BUCKETS.map((option) => (
          <Chip
            key={option.value}
            selected={option.value === bucket}
            onClick={() => {
              setBucket(option.value);
              setShown(PAGE);
            }}
          >
            {option.label} {wallet.buckets[option.value]?.length ?? 0}
          </Chip>
        ))}
      </div>
      <div className="flex w-full flex-col gap-2.5">
        <p className="flex flex-wrap gap-1.5 text-small" aria-live="polite">
          <span className="font-bold text-grey-900">{items.length}건</span>
          <span className="text-grey-600">
            {profileText && `${profileText} 기준으로 판정 · `}
            {wallet.dataAsOf ? `${formatDateTime(wallet.dataAsOf)} 수집 기준` : "수집 기준일 확인 필요"} · 신청 자격과 일정은
            정책 상세와 공식 공고에서 확인해 주세요.
          </span>
        </p>
        {items.length > 0 ? (
          <PolicyTable policies={items.slice(0, shown)} />
        ) : (
          <div className="flex w-full flex-col items-center gap-1 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
            <p className="text-body font-bold text-grey-900">이 묶음에 해당하는 정책이 없어요</p>
          </div>
        )}
        {items.length > shown && (
          <div className="flex justify-center pt-2">
            <Button variant="line" size="M" onClick={() => setShown((n) => n + PAGE)}>
              정책 더 보기 ({items.length - shown}건 남음)
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
