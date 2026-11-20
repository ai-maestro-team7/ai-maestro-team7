import { cn } from "@/lib/cn";

export type StatItem = { label: string; value: number; unit: string };

/** 숫자 요약 줄 (직무 진단 결과, 면접 리포트). 항목 사이 세로선, 숫자는 Num 30px. */
export function Stats({ items, className }: { items: StatItem[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-2 rounded-card border border-grey-200 py-5 sm:grid-cols-4", className)}>
      {items.map((item, index) => (
        <div
          key={item.label}
          className={cn(
            "flex flex-col gap-0.5 px-6",
            index > 0 && "sm:border-l sm:border-grey-200",
            index % 2 === 1 && "border-l border-grey-200",
            index >= 2 && "max-sm:mt-4",
          )}
        >
          <dt className="text-small text-grey-600">{item.label}</dt>
          <dd className="flex items-baseline gap-0.75">
            <span className="text-num font-bold text-grey-900">{item.value}</span>
            <span className="text-body font-medium text-grey-700">{item.unit}</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
