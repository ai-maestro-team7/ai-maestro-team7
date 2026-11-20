import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** 불러오는 동안 내용 자리를 채우는 회색 막대. 크기는 className으로 정한다 (예: "h-4 w-1/2"). */
export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cn("block rounded-control bg-grey-100 motion-safe:animate-pulse", className)} />;
}

/**
 * 스켈레톤 묶음의 바깥 틀. 화면 읽기 프로그램에는 `label`만 읽히고, 막대는 숨긴다.
 * API(Lambda) 응답이 늦을 때 화면이 비어 보이지 않게 쓴다.
 */
export function SkeletonGroup({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="status" aria-live="polite" aria-busy className={cn("w-full", className)}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** 상세·입력 화면처럼 표가 아닌 화면의 스켈레톤: 제목, 설명 한 줄, 내용 묶음 몇 개 */
export function PageSkeleton({ label, sections = 3 }: { label: string; sections?: number }) {
  return (
    <SkeletonGroup label={label} className="flex flex-col gap-8">
      <div className="flex flex-col gap-3.5">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-3/4" />
        <Skeleton className="h-5 w-1/2" />
      </div>
      {Array.from({ length: sections }, (_, index) => (
        <div key={index} className="flex flex-col gap-3 border-t border-grey-200 pt-6">
          <Skeleton className="h-6 w-28" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      ))}
    </SkeletonGroup>
  );
}
