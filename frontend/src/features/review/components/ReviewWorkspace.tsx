"use client";

import Link from "next/link";
import { useState } from "react";
import { SubTabs } from "@/components/ui/SubTabs";
import type { ReviewDocumentKind, ReviewSample } from "../types";

type ReviewWorkspaceProps = {
  samples: ReviewSample[];
  targetRole: string;
};

/** AI 서류 첨삭: 문서 종류 탭 + 원문/개선 예시 비교. */
export function ReviewWorkspace({ samples, targetRole }: ReviewWorkspaceProps) {
  const [kind, setKind] = useState<ReviewDocumentKind>(samples[0].kind);
  const sample = samples.find((item) => item.kind === kind) ?? samples[0];

  return (
    <div className="flex w-full flex-col gap-7">
      <div className="flex w-full flex-col gap-3.5">
        <SubTabs
          label="첨삭할 문서"
          items={samples.map((item) => ({ key: item.kind, label: item.tabLabel }))}
          activeKey={kind}
          onChange={setKind}
          panelId="review-compare"
        />
        <p className="flex items-center gap-2 text-small">
          <span className="text-grey-600">목표 직무</span>
          <span className="font-bold text-grey-900">{targetRole}</span>
          <Link href="/diagnosis" className="font-medium text-blue-500">
            바꾸기
          </Link>
        </p>
      </div>

      <div
        id="review-compare"
        role="tabpanel"
        aria-label={`${sample.tabLabel} 첨삭`}
        className="grid w-full grid-cols-1 overflow-hidden rounded-card border border-grey-200 md:grid-cols-2"
      >
        <section aria-labelledby="review-original" className="flex flex-col gap-3.5 px-6 py-5.5">
          <h2 id="review-original" className="text-small font-bold text-grey-600">
            원문
          </h2>
          <p className="text-body text-grey-700">{sample.original}</p>
          <p className="text-small text-grey-600">{sample.originalNote}</p>
        </section>
        <section
          aria-labelledby="review-improved"
          className="flex flex-col gap-3.5 border-grey-200 px-6 py-5.5 max-md:border-t md:border-l"
        >
          <h2 id="review-improved" className="text-small font-bold text-blue-500">
            개선 예시
          </h2>
          <p className="text-body text-grey-900">{sample.improved}</p>
          <p className="text-small text-grey-600">{sample.improvedNote}</p>
        </section>
      </div>
    </div>
  );
}
