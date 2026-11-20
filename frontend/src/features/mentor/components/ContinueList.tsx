import { ChevronRight } from "lucide-react";
import Link from "next/link";
import type { ContinueItem } from "../types";

/** 홈 "이어서 하기" 목록 (폭 332px 상자 안 링크 4개). */
export function ContinueList({ items }: { items: ContinueItem[] }) {
  return (
    <section aria-labelledby="continue-title" className="flex w-full flex-col gap-2.5 lg:w-rail lg:shrink-0">
      <h2 id="continue-title" className="text-h3 font-bold text-grey-900">
        이어서 하기
      </h2>
      <ul className="flex flex-col rounded-card border border-grey-200 px-5 py-1.5">
        {items.map((item) => (
          <li key={item.href} className="border-b border-grey-200 last:border-b-0">
            <Link href={item.href} className="group flex items-center justify-between gap-3 py-3.5">
              <span className="flex flex-col gap-0.5">
                <span className="text-body font-bold text-grey-900 group-hover:text-blue-500">{item.title}</span>
                <span className="text-small text-grey-600">{item.description}</span>
              </span>
              <ChevronRight aria-hidden className="size-4 shrink-0 text-grey-400" strokeWidth={2} />
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
