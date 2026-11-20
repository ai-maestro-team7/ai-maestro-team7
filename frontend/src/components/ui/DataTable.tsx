import type { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { Skeleton, SkeletonGroup } from "./Skeleton";

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
  headerClassName,
  children,
}: {
  columns: Column[];
  label: string;
  minWidthClassName?: string;
  /** 머리줄에 더할 클래스 (예: 행과 같은 좌우 여백 "px-4") */
  headerClassName?: string;
  children: ReactNode;
}) {
  return (
    <div className="w-full overflow-x-auto">
      <div role="table" aria-label={label} className={cn("w-full border-t border-grey-800", minWidthClassName)}>
        <div role="rowgroup">
          <div
            role="row"
            className={cn("flex items-center gap-4 border-b border-grey-200 bg-grey-50 py-2.5", headerClassName)}
          >
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

/**
 * 표를 불러오는 동안 보여주는 자리. 실제 표와 같은 열 폭과 머리줄을 쓰고, 셀마다 회색 막대 두 줄을 둔다.
 * 아이콘 열(`srOnly`)은 작은 네모 하나만 둔다.
 */
export function DataTableSkeleton({
  columns,
  label,
  rows = 3,
  minWidthClassName,
  headerClassName,
  rowClassName = "py-4",
}: {
  columns: Column[];
  label: string;
  rows?: number;
  minWidthClassName?: string;
  headerClassName?: string;
  rowClassName?: string;
}) {
  return (
    <SkeletonGroup label={label}>
      {/* 빈 표가 읽히지 않게 표 전체를 숨기고 label만 읽힌다 */}
      <div aria-hidden>
        <DataTable
        columns={columns}
        label={label}
        minWidthClassName={minWidthClassName}
        headerClassName={headerClassName}
      >
        {Array.from({ length: rows }, (_, row) => (
          <TableRow key={row} className={rowClassName}>
            {columns.map((column) => (
              <TableCell key={column.key} className={cn(column.className, "flex flex-col gap-0.5")}>
                {column.srOnly ? (
                  <Skeleton className="size-4" />
                ) : (
                  <>
                    {/* 막대 위아래 여백까지 실제 글줄 높이(본문 24px, 작은 글 20px)와 같게 해 불러온 뒤 행 높이가 거의 그대로다 */}
                    <Skeleton className="my-1 h-4 w-4/5" />
                    <Skeleton className="my-1 h-3 w-1/2" />
                  </>
                )}
              </TableCell>
            ))}
          </TableRow>
        ))}
        </DataTable>
      </div>
    </SkeletonGroup>
  );
}
