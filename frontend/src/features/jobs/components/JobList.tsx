"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { formatDate } from "@/lib/format";
import { DATA_AS_OF, jobPostings, RECOMMEND_BASIS } from "../data";
import { filterJobs, JOB_TYPE_FILTERS, SORT_LABELS, sortJobs } from "../lib";
import type { JobSort, JobTypeFilter } from "../types";
import { JobTable } from "./JobTable";

/** 채용 공고 목록: 고용 형태 필터, 정렬 바꾸기, GNB 검색어(`?q=`) 적용. */
export function JobList() {
  const query = useSearchParams().get("q") ?? "";
  const [type, setType] = useState<JobTypeFilter>("전체");
  const [sort, setSort] = useState<JobSort>("RECOMMENDED");

  const jobs = useMemo(() => sortJobs(filterJobs(jobPostings, type, query), sort), [type, query, sort]);

  return (
    <div className="flex w-full flex-col gap-5">
      <div className="flex w-full flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="고용 형태" className="flex flex-wrap gap-2">
          {JOB_TYPE_FILTERS.map((filter) => (
            <Chip key={filter} selected={filter === type} onClick={() => setType(filter)}>
              {filter}
            </Chip>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setSort((value) => (value === "RECOMMENDED" ? "DEADLINE" : "RECOMMENDED"))}
          className="flex h-8.5 items-center gap-2 rounded-control border border-grey-300 px-3 text-small font-medium hover:bg-grey-50"
        >
          <span className="text-grey-800">{SORT_LABELS[sort]}</span>
          <span className="text-blue-500">바꾸기</span>
          <span className="sr-only">(정렬 기준 바꾸기)</span>
        </button>
      </div>

      <div className="flex w-full flex-col gap-2.5">
        <div className="flex w-full flex-wrap items-center justify-between gap-2 text-small">
          <p className="flex gap-1.5" aria-live="polite">
            <span className="font-bold text-grey-900">{jobs.length}건</span>
            <span className="text-grey-600">
              {query && `"${query}" 검색 · `}
              {formatDate(DATA_AS_OF)} 기준 · 예시 데이터
            </span>
          </p>
          <p className="flex gap-2">
            <span className="text-grey-600">
              {RECOMMEND_BASIS.role} · {RECOMMEND_BASIS.skills.join(", ")} 기준으로 추천했어요
            </span>
            <Link href="/diagnosis" className="font-medium text-blue-500">
              프로필 수정
            </Link>
          </p>
        </div>

        {jobs.length > 0 ? (
          <JobTable jobs={jobs} asOf={DATA_AS_OF} />
        ) : (
          <div className="flex w-full flex-col items-center gap-1 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
            <p className="text-body font-bold text-grey-900">조건에 맞는 공고가 없어요</p>
            <p className="text-small text-grey-600">고용 형태나 검색어를 바꿔 보세요.</p>
          </div>
        )}
        <p className="text-small text-grey-600">
          적합도는 이력서의 기술을 공고 요건과 비교한 결과예요. 합격 확률이 아니에요.
        </p>
      </div>
    </div>
  );
}
