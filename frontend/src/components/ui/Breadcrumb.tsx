import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { Fragment } from "react";

type Crumb = { label: string; href?: string };

/** 상세 화면 상단 경로. 앞 항목은 grey-600 링크, 마지막은 grey-800 Medium. */
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="현재 위치">
      <ol className="flex items-center gap-1 text-small">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <Fragment key={item.label}>
              <li>
                {item.href && !last ? (
                  <Link href={item.href} className="text-grey-600 hover:text-grey-800">
                    {item.label}
                  </Link>
                ) : (
                  <span aria-current={last ? "page" : undefined} className="font-medium text-grey-800">
                    {item.label}
                  </span>
                )}
              </li>
              {!last && (
                <li aria-hidden className="text-grey-400">
                  <ChevronRight className="size-3" strokeWidth={2} />
                </li>
              )}
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
