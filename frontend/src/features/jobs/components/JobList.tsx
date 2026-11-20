"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { fetchFeed } from "../data";
import { asOfDate, REGION_FILTERS, SORT_LABELS } from "../lib";
import type { FeedResponse, JobRegion, JobSort, PostingCard } from "../types";
import { JobTable, JobTableSkeleton } from "./JobTable";

type MorePages = { key: string; items: PostingCard[]; nextCursor?: string; pending: boolean; failed: boolean };

/** 채용 공고 목록 (B-03 맞춤 피드): 지역 필터, 정렬 바꾸기, GNB 검색어(`?q=`), 더 보기. */
export function JobList() {
  const params = useSearchParams();
  const query = params.get("q") ?? "";
  const username = useUsername();
  const [region, setRegion] = useState<JobRegion>("ALL");
  const [sort, setSort] = useState<JobSort>("BUSAN_FIRST");
  // 홈의 "지역인재 전형 공고 보기"는 ?talent=1 로 들어온다
  const [talentOnly, setTalentOnly] = useState(params.get("talent") === "1");
  const key = `${username}|${sort}|${region}|${query}|${talentOnly}`;
  const [state, reload] = useApi<FeedResponse>(key, () =>
    fetchFeed({ sort, region, keyword: query, regionalTalent: talentOnly }),
  );
  const [more, setMore] = useState<MorePages | null>(null);
  const extra = more?.key === key ? more : null;

  async function loadMore(first: FeedResponse) {
    const before = extra?.items ?? [];
    const cursor = extra ? extra.nextCursor : first.nextCursor;
    if (!cursor) return;
    setMore({ key, items: before, nextCursor: cursor, pending: true, failed: false });
    try {
      const page = await fetchFeed({ sort, region, keyword: query, cursor, regionalTalent: talentOnly });
      setMore({ key, items: [...before, ...page.items], nextCursor: page.nextCursor, pending: false, failed: false });
    } catch {
      setMore({ key, items: before, nextCursor: cursor, pending: false, failed: true });
    }
  }

  return (
    <div className="flex w-full flex-col gap-5">
      <div className="flex w-full flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="근무 지역" className="flex flex-wrap gap-2">
          {REGION_FILTERS.map((filter) => (
            <Chip key={filter.value} selected={filter.value === region} onClick={() => setRegion(filter.value)}>
              {filter.label}
            </Chip>
          ))}
          <span aria-hidden className="mx-1 h-5 w-px self-center bg-grey-200" />
          <Chip selected={talentOnly} onClick={() => setTalentOnly((value) => !value)}>
            지역인재 전형
          </Chip>
        </div>
        <button
          type="button"
          onClick={() => setSort((value) => (value === "BUSAN_FIRST" ? "DEADLINE" : "BUSAN_FIRST"))}
          className="flex h-8.5 items-center gap-2 rounded-control border border-grey-300 px-3 text-small font-medium hover:bg-grey-50"
        >
          <span className="text-grey-800">{SORT_LABELS[sort]}</span>
          <span className="text-blue-500">바꾸기</span>
          <span className="sr-only">(정렬 기준 바꾸기)</span>
        </button>
      </div>

      {state.status === "loading" && <JobTableSkeleton rows={6} />}
      {state.status === "error" && <ApiErrorNotice error={state.error} onRetry={reload} />}
      {state.status === "success" && (
        <FeedResult
          feed={state.data}
          items={[...state.data.items, ...(extra?.items ?? [])]}
          query={query}
          sort={sort}
          talentOnly={talentOnly}
          hasMore={Boolean(extra ? extra.nextCursor : state.data.nextCursor)}
          pending={extra?.pending ?? false}
          failed={extra?.failed ?? false}
          onMore={() => loadMore(state.data)}
        />
      )}
    </div>
  );
}

function FeedResult({
  feed,
  items,
  query,
  sort,
  talentOnly,
  hasMore,
  pending,
  failed,
  onMore,
}: {
  feed: FeedResponse;
  items: PostingCard[];
  query: string;
  sort: JobSort;
  talentOnly: boolean;
  hasMore: boolean;
  pending: boolean;
  failed: boolean;
  onMore: () => void;
}) {
  // emptyMessage 뒤쪽의 "새 공고 알림 받기"는 알림 화면이 아직 없어 앞 문장만 보여준다
  const notice = feed.emptyMessage?.split(" · ")[0];

  return (
    <div className="flex w-full flex-col gap-2.5">
      <div className="flex w-full flex-wrap items-center justify-between gap-2 text-small">
        <p className="flex flex-wrap gap-1.5" aria-live="polite">
          <span className="font-bold text-grey-900">{items.length}건</span>
          <span className="text-grey-600">
            {query && `"${query}" 검색 · `}
            {feed.dataAsOf ? `${formatDateTime(feed.dataAsOf)} 수집 기준` : "수집 기준일 확인 필요"}
            {feed.stale && " · 최신 수집이 늦어지고 있어요"}
          </span>
        </p>
        <p className="flex gap-2">
          {sort === "BUSAN_FIRST" && <span className="text-grey-600">{feed.ranking.basis}</span>}
          <Link href="/profile/?next=%2Fjobs%2F" className="font-medium text-blue-500">
            프로필 수정
          </Link>
        </p>
      </div>
      {notice && <p className="text-small text-grey-700">{notice}</p>}
      {talentOnly && (
        <p className="text-small text-grey-700">
          이전 공공기관처럼 지역인재 전형이 있을 수 있는 공고예요. 학교 지역이 맞으면 &ldquo;지역인재 대상일 수 있음&rdquo;으로
          표시해요. 자격은 공고문에서 확인해 주세요.
        </p>
      )}
      {items.length > 0 ? (
        <JobTable jobs={items} asOf={asOfDate(feed.dataAsOf)} />
      ) : (
        <div className="flex w-full flex-col items-center gap-1 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
          <p className="text-body font-bold text-grey-900">조건에 맞는 공고가 없어요</p>
          <p className="text-small text-grey-600">
            {talentOnly ? "지역인재 전형이 있을 수 있는 공고가 지금은 없어요." : "지역이나 검색어를 바꿔 보세요."}
          </p>
        </div>
      )}
      {hasMore && (
        <div className="flex flex-col items-center gap-1.5 pt-2">
          <Button variant="line" size="M" onClick={onMore} disabled={pending}>
            {pending ? "불러오는 중" : "공고 더 보기"}
          </Button>
          {failed && (
            <p role="alert" className="text-small text-red-500">
              더 불러오지 못했어요. 다시 눌러 주세요.
            </p>
          )}
        </div>
      )}
      <p className="text-small text-grey-600">
        적합도는 내 프로필을 공고 요건과 비교한 결과예요. 합격 확률이 아니에요.
      </p>
    </div>
  );
}
