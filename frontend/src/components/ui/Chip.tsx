import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

type ChipProps = Omit<ButtonHTMLAttributes<HTMLButtonElement>, "type"> & {
  /** 필터처럼 켜고 끄는 Chip이면 선택 상태를 넘긴다. 넘기면 `aria-pressed`가 붙는다. */
  selected?: boolean;
};

/** 예시 질문·필터 Chip (높이 34px). 선택되면 grey-900 배경. */
export function Chip({ selected, className, children, ...rest }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "inline-flex h-8.5 shrink-0 items-center justify-center whitespace-nowrap rounded-control border px-3 text-small font-medium transition-colors",
        selected
          ? "border-grey-900 bg-grey-900 text-white hover:bg-grey-800"
          : "border-grey-300 bg-white text-grey-800 hover:border-grey-400 hover:bg-grey-50",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}
