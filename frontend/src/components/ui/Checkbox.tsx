import { Check } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

type CheckboxProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
  /** 상자와 글 사이 간격. 동의 항목 10px, 체크리스트 12px */
  gapClassName?: string;
  className?: string;
};

/** 20px 체크박스. 실제 `<input type="checkbox">`를 숨기고 같은 모양의 상자를 보여준다. */
export function Checkbox({ checked, onChange, children, gapClassName = "gap-2.5", className }: CheckboxProps) {
  return (
    <label className={cn("flex cursor-pointer items-start", gapClassName, className)}>
      <input
        type="checkbox"
        className="peer sr-only"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span
        aria-hidden
        className={cn(
          "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-check peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-blue-500",
          checked ? "bg-blue-500" : "border-[1.5px] border-grey-400 bg-white",
        )}
      >
        {checked && <Check className="size-3.5 text-white" strokeWidth={3} />}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">{children}</span>
    </label>
  );
}
