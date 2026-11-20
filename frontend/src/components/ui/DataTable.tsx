import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Column = {
  key: string;
  label: string;
  /** 열 폭 (예: "w-45"). 없으면 남은 폭을 채운다 */
  className?: string;
  /** 화면에 보이지 않는 열 이름 (아이콘 열) */
  srOnly?: boolean;
};

/**
 * 공고·정책·진단 표의 틀. 위쪽 1px grey-800 선, grey-50 머리줄, 행 사이 grey-200 선.
 * 좁은 화면에서는 가로로 스크롤한다. 행은 `TableRow`로 만든다.
 */
export function DataTable({
  columns,
  label,
  minWidthClassName = "min-w-240",
  children,
}: {
  columns: Column[];
  label: string;
  minWidthClassName?: string;
  children: ReactNode;
}) {
  return (
    <div className="w-full overflow-x-auto">
      <div role="table" aria-label={label} className={cn("w-full border-t border-grey-800", minWidthClassName)}>
        <div role="rowgroup">
          <div role="row" className="flex items-center gap-4 border-b border-grey-200 bg-grey-50 py-2.5">
            {columns.map((column) => (
              <div
                key={column.key}
                role="columnheader"
                className={cn(
                  "text-small font-medium text-grey-600",
                  column.className ?? "min-w-0 flex-1",
                )}
              >
                {column.srOnly ? <span className="sr-only">{column.label}</span> : column.label}
              </div>
            ))}
          </div>
        </div>
        <div role="rowgroup">{children}</div>
      </div>
    </div>
  );
}

/** `DataTable`의 행. 셀은 `TableCell`로 감싼다. */
export function TableRow({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <div role="row" className={cn("flex items-center gap-4 border-b border-grey-200", className)}>
      {children}
    </div>
  );
}

export function TableCell({ className, children }: { className?: string; children?: ReactNode }) {
  return (
    <div role="cell" className={cn(className ?? "min-w-0 flex-1")}>
      {children}
    </div>
  );
}
