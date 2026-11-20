import type { HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type PanelProps = HTMLAttributes<HTMLDivElement> & {
  /** outline: grey-200 테두리 + 흰 배경, muted: grey-50 배경 (테두리 없음) */
  tone?: "outline" | "muted";
  as?: "div" | "section" | "aside";
};

/** 모서리 12px 상자. 오른쪽 요약 상자, 안내 상자에서 쓴다. 안쪽 여백은 쓰는 곳에서 준다. */
export function Panel({ tone = "outline", as: Tag = "div", className, ...rest }: PanelProps) {
  return (
    <Tag
      className={cn(
        "rounded-card",
        tone === "outline" ? "border border-grey-200 bg-white" : "bg-grey-50",
        className,
      )}
      {...rest}
    />
  );
}
