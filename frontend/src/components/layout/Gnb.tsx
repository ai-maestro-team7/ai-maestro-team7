"use client";

import { Bell, Bookmark, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { demoUser } from "@/features/user/data";
import { cn } from "@/lib/cn";
import { activeNavHref, NAV_ITEMS } from "./navigation";

/** 상단 공통 메뉴 (Figma GNB 27:1616). 높이 64px 윗줄 + 48px 탭 줄. */
export function Gnb() {
  const pathname = usePathname();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const activeHref = activeNavHref(pathname);

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    router.push(q ? `/jobs?q=${encodeURIComponent(q)}` : "/jobs");
  }

  return (
    <header className="w-full border-b border-grey-200 bg-white">
      <div className="mx-auto flex w-full max-w-content flex-wrap items-center justify-between gap-x-7 gap-y-3 px-5 py-3 xl:px-0 lg:h-16 lg:py-0">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-7 gap-y-3">
          <Link href="/" className="text-logo font-bold text-blue-500">
            부산커리어
          </Link>
          <form role="search" onSubmit={handleSearch} className="relative w-full sm:w-85">
            <label htmlFor="gnb-search" className="sr-only">
              공고, 정책 검색
            </label>
            <input
              id="gnb-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="공고, 정책 검색"
              className="h-10 w-full rounded-control border border-grey-300 bg-white pr-10 pl-3.5 text-small text-grey-900 placeholder:text-grey-500 focus:border-blue-500 focus:outline-none"
            />
            <button
              type="submit"
              aria-label="검색"
              className="absolute top-1/2 right-3 -translate-y-1/2 text-grey-700"
            >
              <Search className="size-4.5" strokeWidth={2} aria-hidden />
            </button>
          </form>
        </div>
        <div className="flex items-center gap-5 text-small">
          {/* 저장한 공고·알림은 Figma에 이동할 화면이 없어 표시만 한다 (requirements 열린 항목) */}
          <span className="hidden items-center gap-1 text-grey-700 md:flex">
            <Bookmark className="size-4" strokeWidth={2} aria-hidden />
            저장한 공고
          </span>
          <span className="hidden items-center gap-1 text-grey-700 md:flex">
            <Bell className="size-4" strokeWidth={2} aria-hidden />
            알림
          </span>
          <span aria-hidden className="hidden h-3 w-px bg-grey-300 md:block" />
          <span className="font-medium text-grey-900">{demoUser.displayName} 님</span>
          <span className="text-grey-500">시연 모드</span>
        </div>
      </div>
      <nav aria-label="주 메뉴" className="mx-auto w-full max-w-content px-5 xl:px-0">
        <ul className="flex gap-7 overflow-x-auto">
          {NAV_ITEMS.map((item) => {
            const active = item.href === activeHref;
            return (
              <li key={item.href} className="shrink-0">
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "flex h-12 items-center whitespace-nowrap border-b-2 text-body",
                    active
                      ? "border-blue-500 font-bold text-blue-500"
                      : "border-transparent font-medium text-grey-800 hover:text-grey-900",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </header>
  );
}
