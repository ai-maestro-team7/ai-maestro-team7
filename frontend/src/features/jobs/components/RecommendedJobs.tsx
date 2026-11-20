"use client";

import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { useApi } from "@/lib/useApi";
import { fetchFeed } from "../data";
import { asOfDate, BUSAN_FIRST_BASIS, SORT_LABELS } from "../lib";
import type { FeedResponse } from "../types";
import { JobTable, JobTableSkeleton } from "./JobTable";

const HOME_COUNT = 3;

/** 홈 "나와 맞는 부산 공고": 부산 우선 추천순 상위 3개 */
export function RecommendedJobs() {
  const username = useUsername();
  const [state, reload] = useApi<FeedResponse>(`${username}|home`, () =>
    fetchFeed({ sort: "BUSAN_FIRST", region: "ALL", limit: HOME_COUNT }),
  );

  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;
  return (
    <>
      {/* 정렬 기준 문구는 응답 전에도 보여 줘 표가 밀리지 않게 한다 */}
      <p className="text-small text-grey-600">
        {SORT_LABELS.BUSAN_FIRST} · {state.status === "success" ? state.data.ranking.basis : BUSAN_FIRST_BASIS}
      </p>
      {state.status === "success" ? (
        <JobTable jobs={state.data.items.slice(0, HOME_COUNT)} asOf={asOfDate(state.data.dataAsOf)} />
      ) : (
        <JobTableSkeleton rows={HOME_COUNT} />
      )}
    </>
  );
}

/** 홈 Suspense 대체 화면. 불러오는 중 화면과 같은 높이다. */
export function RecommendedJobsLoading() {
  return (
    <>
      <p className="text-small text-grey-600">
        {SORT_LABELS.BUSAN_FIRST} · {BUSAN_FIRST_BASIS}
      </p>
      <JobTableSkeleton rows={HOME_COUNT} />
    </>
  );
}
