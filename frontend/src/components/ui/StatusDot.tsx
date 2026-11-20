import { cn } from "@/lib/cn";

export type StatusTone = "orange" | "green" | "red" | "blue";

const tones: Record<StatusTone, string> = {
  orange: "bg-orange-500",
  green: "bg-green-500",
  red: "bg-red-500",
  blue: "bg-blue-500",
};

/** 6px 색 점 + 상태 글 (Small M, grey-800). 정책 상태·진단 상태에서 쓴다. */
export function StatusDot({ tone, label, className }: { tone: StatusTone; label: string; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-small font-medium text-grey-800", className)}>
      <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", tones[tone])} />
      {label}
    </span>
  );
}
