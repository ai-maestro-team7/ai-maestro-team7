import Link from "next/link";
import { cn } from "@/lib/cn";

export type SubTabItem<K extends string> = { key: K; label: string; href?: string };

type SubTabsProps<K extends string> = {
  items: SubTabItem<K>[];
  activeKey: K;
  /** 같은 화면 안에서 바꾸는 탭이면 넘긴다. `href`가 있는 탭은 링크로 이동한다. */
  onChange?: (key: K) => void;
  /** 탭 패널 id 접두사 (화면 안 탭일 때 `aria-controls`에 쓴다) */
  panelId?: string;
  label: string;
  className?: string;
};

/** 화면 안 하위 탭. 현재 탭은 grey-900 Bold + 2px 밑줄, 나머지는 grey-600 Medium. 높이 44px. */
export function SubTabs<K extends string>({ items, activeKey, onChange, panelId, label, className }: SubTabsProps<K>) {
  const isLinkTabs = items.every((item) => item.href);

  return (
    <div
      role={isLinkTabs ? undefined : "tablist"}
      aria-label={label}
      className={cn("flex w-full gap-6 overflow-x-auto border-b border-grey-200", className)}
    >
      {items.map((item) => {
        const active = item.key === activeKey;
        const classes = cn(
          "-mb-px flex h-11 shrink-0 items-center whitespace-nowrap border-b-2 text-body transition-colors",
          active
            ? "border-grey-900 font-bold text-grey-900"
            : "border-transparent font-medium text-grey-600 hover:border-grey-300 hover:text-grey-800",
        );

        if (item.href) {
          return (
            <Link key={item.key} href={item.href} aria-current={active ? "page" : undefined} className={classes}>
              {item.label}
            </Link>
          );
        }
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            aria-controls={panelId}
            onClick={() => onChange?.(item.key)}
            className={classes}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}
