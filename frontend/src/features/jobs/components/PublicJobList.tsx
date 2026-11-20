"use client";

import { Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, type ReactNode, Suspense, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { cn } from "@/lib/cn";
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
type FilterKey = keyof Filters;
const FILTER_KEYS: FilterKey[] = ["sector", "region", "career", "employment"];

type MorePages = { key: string; items: PublicPostingCard[]; nextCursor?: string; pending: boolean; failed: boolean };

/** 주소 값이 보기에 있으면 그 값, 아니면 전체 */
function pick<V extends string>(value: string | null, options: { value: V }[]): V {
  return options.find((option) => option.value === value)?.value ?? options[0].value;
}

/**
 * 로그인 없이 보는 채용 공고 목록. 검색어와 공기업·사기업, 지역, 경력, 고용 형태로 나눠 본다. 마감 임박순 하나다.
 * 검색어와 분류는 주소(`?q=&sector=&region=&career=&employment=`)에 둔다. 그래서 GNB 검색과 화면 안 검색이 같은 목록을 보고,
 * 공고 상세를 보고 뒤로 와도 고른 분류가 그대로 남는다. 내 프로필에 맞춘 순서와 적합도는 맞춤형 공고(로그인)에서 본다.
 */
export function PublicJobList() {
  return (
    <Suspense
      fallback={
        <div className="flex w-full flex-col gap-5">
          <Skeleton className="h-62 w-full rounded-card" />
          <ListFrame />
        </div>
      }
    >
      <Browser />
    </Suspense>
  );
}

function Browser() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filters: Filters = {
    sector: pick(params.get("sector"), SECTOR_FILTERS),
    region: pick(params.get("region"), REGION_FILTERS),
    career: pick(params.get("career"), CAREER_FILTERS),
    employment: pick(params.get("employment"), EMPLOYMENT_FILTERS),
  };
  const query = params.get("q")?.trim() ?? "";
  const activeCount = FILTER_KEYS.filter((key) => filters[key] !== "ALL").length + (query ? 1 : 0);

  /** 주소만 바꾼다 (기록을 쌓지 않고, 스크롤도 그대로) */
  function update(next: Partial<Filters & { q: string }>) {
    const search = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(next)) {
      if (!value || value === "ALL") search.delete(key);
      else search.set(key, value);
    }
    const qs = search.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }
  const resetAll = () => router.replace(pathname, { scroll: false });

  return (
    <div className="flex w-full flex-col gap-5">
      <Panel role="group" aria-label="공고 검색과 분류" className="flex w-full flex-col gap-3 px-5 py-4">
        {/* 주소의 검색어가 바뀌면(GNB 검색) 입력칸도 새로 그린다 */}
        <SearchRow key={query} query={query} onSearch={(q) => update({ q })} />
        <FilterRow label="구분" options={SECTOR_FILTERS} value={filters.sector} onChange={(v) => update({ sector: v })} />
        <FilterRow label="지역" options={REGION_FILTERS} value={filters.region} onChange={(v) => update({ region: v })} />
        <FilterRow label="경력" options={CAREER_FILTERS} value={filters.career} onChange={(v) => update({ career: v })} />
        <FilterRow
          label="고용 형태"
          options={EMPLOYMENT_FILTERS}
          value={filters.employment}
          onChange={(v) => update({ employment: v })}
        />
        {activeCount > 0 && (
          <div className="flex justify-end border-t border-grey-100 pt-3">
            <button
              type="button"
              onClick={resetAll}
              className="flex items-center gap-1 rounded-control px-2 py-1 text-small font-medium text-grey-600 transition-colors hover:bg-grey-50 hover:text-grey-900"
            >
              <X aria-hidden className="size-3.5" strokeWidth={2.2} />
              조건 {activeCount}개 모두 지우기
            </button>
          </div>
        )}
      </Panel>
      <Results filters={filters} query={query} onReset={resetAll} />
    </div>
  );
}

function SearchRow({ query, onSearch }: { query: string; onSearch: (q: string) => void }) {
  const [draft, setDraft] = useState(query);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSearch(draft.trim());
  }

  return (
    <form role="search" onSubmit={submit} className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <label htmlFor="jobs-search" className="w-16 shrink-0 text-small font-medium text-grey-600">
        검색
      </label>
      <div className="relative w-full max-w-120 flex-1">
        <input
          id="jobs-search"
          type="search"
          value={draft}
          maxLength={50}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="기업 이름, 공고 제목, 직무로 찾기"
          className="h-10 w-full rounded-control border border-grey-300 bg-white pr-18 pl-3.5 text-small text-grey-900 transition-colors placeholder:text-grey-500 hover:border-grey-400 focus:border-blue-500 focus:outline-none [&::-webkit-search-cancel-button]:hidden"
        />
        {draft && (
          <button
            type="button"
            aria-label="검색어 지우기"
            onClick={() => {
              setDraft("");
              if (query) onSearch("");
            }}
            className="absolute top-1/2 right-10 -translate-y-1/2 rounded-full p-1 text-grey-500 transition-colors hover:bg-grey-100 hover:text-grey-800"
          >
            <X aria-hidden className="size-4" strokeWidth={2} />
          </button>
        )}
        <button
          type="submit"
          aria-label="검색"
          className="absolute top-1/2 right-3 -translate-y-1/2 text-grey-700 transition-colors hover:text-blue-500"
        >
          <Search aria-hidden className="size-4.5" strokeWidth={2} />
        </button>
      </div>
    </form>
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

function Results({ filters, query, onReset }: { filters: Filters; query: string; onReset: () => void }) {
  const key = `${filters.sector}|${filters.region}|${filters.career}|${filters.employment}|${query}`;
  const [state, reload, previous] = useApi<PublicPostingList>(key, () =>
    fetchPublicPostings({ ...filters, keyword: query }),
  );
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
  // 조건을 바꿔 다시 부르는 동안에는 앞선 목록을 흐리게 둔다. 처음 부를 때만 막대 화면을 보여 준다
  const refreshing = state.status === "loading";
  const list = state.status === "success" ? state.data : previous;
  if (!list) return <ListFrame />;

  const items = refreshing ? list.items : [...list.items, ...(extra?.items ?? [])];
  const hasMore = !refreshing && Boolean(extra ? extra.nextCursor : list.nextCursor);
  const filtered = FILTER_KEYS.some((name) => filters[name] !== "ALL");
  return (
    <ListFrame
      busy={refreshing}
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
          <p className="text-small text-grey-600">검색어나 분류를 바꿔 보세요.</p>
          {(filtered || query) && (
            <Button variant="line" size="M" onClick={onReset}>
              조건 모두 지우기
            </Button>
          )}
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
function ListFrame({ summary, busy = false, children }: { summary?: ReactNode; busy?: boolean; children?: ReactNode }) {
  return (
    <div className="flex w-full flex-col gap-2.5">
      <div className="flex w-full flex-wrap items-center justify-between gap-2 text-small">
        <p className="flex flex-wrap gap-1.5" aria-live="polite">
          {summary ?? <Skeleton className="my-0.5 h-4 w-52" />}
        </p>
        <Link href="/jobs/recommended" className="font-medium text-blue-500 hover:underline">
          내 프로필에 맞춘 공고 보기
        </Link>
      </div>
      <div aria-busy={busy} className={cn("transition-opacity duration-200", busy && "pointer-events-none opacity-50")}>
        {children ?? <PublicJobTableSkeleton />}
      </div>
      <p className="text-small text-grey-600">
        공기업은 공공기관과 지방공공기관(도시공사·시설공단 등), 사기업은 민간 기업이에요. 기업 공고는 각 회사의 공식 채용
        페이지에서 모았어요.
      </p>
    </div>
  );
}
