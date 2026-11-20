import type { ReactNode } from "react";
import { Panel } from "./Panel";

type NextStepPanelProps = {
  eyebrow: string;
  title: string;
  description: string;
  /** 아래 버튼들 (Button L, fullWidth) */
  actions: ReactNode;
};

/** 오른쪽 "다음에 할 일" 상자 (직무 진단 결과, 면접 리포트). */
export function NextStepPanel({ eyebrow, title, description, actions }: NextStepPanelProps) {
  return (
    <Panel as="aside" aria-label={eyebrow} className="flex flex-col p-5">
      <p className="text-small text-grey-600">{eyebrow}</p>
      <p className="mt-3.5 text-h3 font-bold text-grey-900">{title}</p>
      <p className="mt-3.5 text-body text-grey-700">{description}</p>
      <div className="mt-4.5 flex flex-col gap-2">{actions}</div>
    </Panel>
  );
}
