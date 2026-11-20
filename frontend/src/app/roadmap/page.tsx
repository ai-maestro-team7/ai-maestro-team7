import { ArrowRight } from "lucide-react";
import type { Metadata } from "next";
import { Fragment } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { roadmap } from "@/features/roadmap/data";

export const metadata: Metadata = { title: "학습 로드맵" };

export default function RoadmapPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="학습 로드맵" description={`목표 직무 ${roadmap.targetRole} · ${roadmap.basis}`} />

      <Panel as="section" tone="muted" aria-labelledby="roadmap-order" className="flex flex-col gap-1.5 px-5 py-4">
        <h2 id="roadmap-order" className="text-small text-grey-600">
          추천 순서
        </h2>
        <ol className="flex flex-wrap items-center gap-2.5 text-body font-bold text-grey-900">
          {roadmap.order.map((step, index) => (
            <Fragment key={step}>
              <li>{step}</li>
              {index < roadmap.order.length - 1 && (
                <li aria-hidden className="text-grey-500">
                  <ArrowRight className="size-4" strokeWidth={2} />
                </li>
              )}
            </Fragment>
          ))}
        </ol>
      </Panel>

      <ol aria-label="주차별 학습 계획" className="flex w-full flex-col border-t border-grey-800">
        {roadmap.weeks.map((week) => (
          <li
            key={week.week}
            className="flex flex-col gap-2 border-b border-grey-200 py-5.5 last:border-b-0 sm:flex-row sm:gap-6"
          >
            <p className="w-18 shrink-0 text-body font-bold text-blue-500">{week.week}주차</p>
            <div className="flex min-w-0 flex-1 flex-col gap-1.5">
              <h2 className="text-body font-bold text-grey-900">{week.title}</h2>
              <p className="text-body text-grey-700">{week.description}</p>
              <p className="flex gap-2 text-small">
                <span className="text-grey-600">산출물</span>
                <span className="font-bold text-grey-800">{week.deliverable}</span>
              </p>
            </div>
            <p className="shrink-0 text-small text-grey-600 sm:w-42.5 sm:text-right">{week.gap}</p>
          </li>
        ))}
      </ol>

      <div className="flex w-full flex-wrap justify-end gap-2">
        <Button href="/diagnosis/result" variant="secondary">
          직무 진단 결과
        </Button>
        <Button href="/jobs">부산 채용 공고 보기</Button>
      </div>
    </PageContainer>
  );
}
