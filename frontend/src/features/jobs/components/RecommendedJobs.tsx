"use client";

import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { useApi } from "@/lib/useApi";
import { fetchFeed } from "../data";
import { asOfDate, SORT_LABELS } from "../lib";
import type { FeedResponse } from "../types";
import { JobTable, JobTableSkeleton } from "./JobTable";

const HOME_COUNT = 3;

/** 홈 "나와 맞는 부산 공고": 부산 우선 추천순 상위 3개 */
export function RecommendedJobs() {
  const username = useUsername();
  const [state, reload] = useApi<FeedResponse>(`${username}|home`, () =>
    fetchFeed({ sort: "BUSAN_FIRST", region: "ALL", limit: HOME_COUNT }),
  );

  if (state.status === "loading") return <JobTableSkeleton rows={HOME_COUNT} />;
  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;
  return (
    <>
      <p className="text-small text-grey-600">
        {SORT_LABELS.BUSAN_FIRST} · {state.data.ranking.basis}
      </p>
      <JobTable jobs={state.data.items.slice(0, HOME_COUNT)} asOf={asOfDate(state.data.dataAsOf)} />
    </>
  );
}
