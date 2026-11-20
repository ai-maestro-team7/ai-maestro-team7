"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { fetchPublicPostings } from "../data";
import { asOfDate, CAREER_FILTERS, EMPLOYMENT_FILTERS, REGION_FILTERS, SECTOR_FILTERS } from "../lib";
import type {
  CareerFilter,
  EmploymentFilter,
  JobRegion,
  JobSector,
  PublicPostingCard,
  PublicPostingList,
} from "../types";
import { PublicJobTable, PublicJobTableSkeleton } from "./PublicJobTable";

type Filters = { sector: JobSector; region: JobRegion; career: CareerFilter; employment: EmploymentFilter };
const NO_FILTERS: Filters = { sector: "ALL", region: "ALL", career: "ALL", employment: "ALL" };

type MorePages = { key: string; items: PublicPostingCard[]; nextCursor?: string; pending: boolean; failed: boolean };

/**
 * 로그인 없이 보는 채용 공고 목록. 공기업·사기업, 지역, 경력, 고용 형태로 나눠 보고 GNB 검색어(`?q=`)로 찾는다.
 * 마감 임박순 하나로 보여 준다. 내 프로필에 맞춘 순서와 적합도는 맞춤형 공고(로그인)에서 본다.
 */
export function PublicJobList() {
  const [filters, setFilters] = useState<Filters>(NO_FILTERS);
  const choose = <K extends keyof Filters>(key: K) => (value: Filters[K]) =>
    setFilters((current) => ({ ...current, [key]: value }));

  return (
    <div className="flex w-full flex-col gap-5">
      <Panel role="group" aria-label="공고 분류" className="flex w-full flex-col gap-3 px-5 py-4">
        <FilterRow label="구분" options={SECTOR_FILTERS} value={filters.sector} onChange={choose("sector")} />
        <FilterRow label="지역" options={REGION_FILTERS} value={filters.region} onChange={choose("region")} />
        <FilterRow label="경력" options={CAREER_FILTERS} value={filters.career} onChange={choose("career")} />
        <FilterRow
          label="고용 형태"
          options={EMPLOYMENT_FILTERS}
          value={filters.employment}
          onChange={choose("employment")}
        />
      </Panel>
      {/* 검색어(?q=)를 읽는 아래쪽만 Suspense 안에 둔다. 대체 화면은 불러오는 중 화면과 같다 */}
      <Suspense fallback={<ListFrame />}>
        <Results filters={filters} onReset={() => setFilters(NO_FILTERS)} />
      </Suspense>
    </div>
  );
}

function FilterRow<V extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { value: V; label: string }[];
  value: V;
  onChange: (value: V) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <span className="w-16 shrink-0 text-small font-medium text-grey-600">{label}</span>
      <div role="group" aria-label={label} className="flex flex-wrap gap-2">
        {options.map((option) => (
          <Chip key={option.value} selected={option.value === value} onClick={() => onChange(option.value)}>
            {option.label}
          </Chip>
        ))}
      </div>
    </div>
  );
}

function Results({ filters, onReset }: { filters: Filters; onReset: () => void }) {
  const query = useSearchParams().get("q")?.trim() ?? "";
  const key = `${filters.sector}|${filters.region}|${filters.career}|${filters.employment}|${query}`;
  const [state, reload] = useApi<PublicPostingList>(key, () => fetchPublicPostings({ ...filters, keyword: query }));
  const [more, setMore] = useState<MorePages | null>(null);
  const extra = more?.key === key ? more : null;

  async function loadMore(first: PublicPostingList) {
    const before = extra?.items ?? [];
    const cursor = extra ? extra.nextCursor : first.nextCursor;
    if (!cursor) return;
    setMore({ key, items: before, nextCursor: cursor, pending: true, failed: false });
    try {
      const page = await fetchPublicPostings({ ...filters, keyword: query, cursor });
      setMore({ key, items: [...before, ...page.items], nextCursor: page.nextCursor, pending: false, failed: false });
    } catch {
      setMore({ key, items: before, nextCursor: cursor, pending: false, failed: true });
    }
  }

  if (state.status === "error") return <ApiErrorNotice error={state.error} onRetry={reload} />;
  if (state.status === "loading") return <ListFrame />;

  const list = state.data;
  const items = [...list.items, ...(extra?.items ?? [])];
  const hasMore = Boolean(extra ? extra.nextCursor : list.nextCursor);
  const filtered = Object.values(filters).some((value) => value !== "ALL");
  return (
    <ListFrame
      summary={
        <>
          <span className="font-bold text-grey-900">{list.total.toLocaleString("ko-KR")}건</span>
          <span className="text-grey-600">
            {query && `"${query}" 검색 · `}
            마감 임박순
            {list.dataAsOf ? ` · ${formatDateTime(list.dataAsOf)} 수집 기준` : " · 수집 기준일 확인 필요"}
            {list.stale && " · 최신 수집이 늦어지고 있어요"}
          </span>
        </>
      }
    >
      {items.length > 0 ? (
        <PublicJobTable jobs={items} asOf={asOfDate(list.dataAsOf)} />
      ) : (
        <div className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
          <p className="text-body font-bold text-grey-900">조건에 맞는 공고가 없어요</p>
          <p className="text-small text-grey-600">분류나 검색어를 바꿔 보세요.</p>
          <div className="flex gap-2">
            {filtered && (
              <Button variant="line" size="M" onClick={onReset}>
                분류 처음으로
              </Button>
            )}
            {query && (
              <Button href="/jobs" variant="line" size="M">
                검색어 지우기
              </Button>
            )}
          </div>
        </div>
      )}
      {hasMore && (
        <div className="flex flex-col items-center gap-1.5 pt-2">
          <Button variant="line" size="M" onClick={() => loadMore(list)} disabled={extra?.pending}>
            {extra?.pending ? "불러오는 중" : "공고 더 보기"}
          </Button>
          {extra?.failed && (
            <p role="alert" className="text-small text-red-500">
              더 불러오지 못했어요. 다시 눌러 주세요.
            </p>
          )}
        </div>
      )}
    </ListFrame>
  );
}

/** 건수 줄 + 표 + 안내의 틀. 불러오는 중에는 건수 자리만 막대로 두어 응답이 와도 표 위치가 바뀌지 않는다. */
function ListFrame({ summary, children }: { summary?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex w-full flex-col gap-2.5">
      <div className="flex w-full flex-wrap items-center justify-between gap-2 text-small">
        <p className="flex flex-wrap gap-1.5" aria-live="polite">
          {summary ?? <Skeleton className="my-0.5 h-4 w-52" />}
        </p>
        <Link href="/jobs/recommended" className="font-medium text-blue-500">
          내 프로필에 맞춘 공고 보기
        </Link>
      </div>
      {children ?? <PublicJobTableSkeleton />}
      <p className="text-small text-grey-600">
        공기업은 공공기관과 지방공공기관(도시공사·시설공단 등), 사기업은 민간 기업이에요. 기업 공고는 각 회사의 공식 채용
        페이지에서 모았어요.
      </p>
    </div>
  );
}
