"use client";

import { useState } from "react";
import { Checkbox } from "@/components/ui/Checkbox";
import type { PolicyChecklistItem } from "../types";

/** 지원 조건 체크리스트. 체크 상태는 화면 안에서만 유지한다 (저장하지 않음). */
export function PolicyChecklist({ items }: { items: PolicyChecklistItem[] }) {
  const [checked, setChecked] = useState<boolean[]>(() => items.map(() => false));

  return (
    <section aria-labelledby="policy-checklist" className="flex flex-col gap-1 border-t border-grey-200 pt-6">
      <h2 id="policy-checklist" className="text-h3 font-bold text-grey-900">
        지원 조건 체크리스트
      </h2>
      <ul className="flex flex-col">
        {items.map((item, index) => (
          <li key={item.title} className="border-b border-grey-200 py-4 last:border-b-0">
            <Checkbox
              gapClassName="gap-3"
              checked={checked[index]}
              onChange={(value) => setChecked((prev) => prev.map((v, i) => (i === index ? value : v)))}
            >
              <span className="text-body font-bold text-grey-900">{item.title}</span>
              <span className="mt-0.5 text-body text-grey-700">{item.description}</span>
            </Checkbox>
          </li>
        ))}
      </ul>
    </section>
  );
}
