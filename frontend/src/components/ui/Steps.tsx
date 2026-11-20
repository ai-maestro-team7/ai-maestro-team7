import { ChevronRight } from "lucide-react";
import { Fragment } from "react";
import { cn } from "@/lib/cn";

export type StepNumber = 1 | 2 | 3 | 4;

const STEP_LABELS = ["설정", "장비 점검", "면접", "리포트"] as const;

/**
 * Figma Steps(27:1399). 현재 단계는 blue-500 Bold, 지난 단계는 grey-800, 다음 단계는 grey-500.
 */
export function Steps({ current }: { current: StepNumber }) {
  return (
    <ol aria-label="모의면접 단계" className="flex items-center gap-2.5 text-small">
      {STEP_LABELS.map((label, index) => {
        const step = index + 1;
        const state = step === current ? "current" : step < current ? "done" : "todo";
        return (
          <Fragment key={label}>
            <li
              aria-current={state === "current" ? "step" : undefined}
              className={cn(
                "whitespace-pre",
                state === "current" && "font-bold text-blue-500",
                state === "done" && "text-grey-800",
                state === "todo" && "text-grey-500",
              )}
            >
              {`${step}  ${label}`}
            </li>
            {step < STEP_LABELS.length && (
              <li aria-hidden className="text-grey-400">
                <ChevronRight className="size-3" strokeWidth={2} />
              </li>
            )}
          </Fragment>
        );
      })}
    </ol>
  );
}
