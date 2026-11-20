import type { Metadata } from "next";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { ReviewWorkspace } from "@/features/review/components/ReviewWorkspace";
import { REVIEW_TARGET_ROLE, reviewNextStep, reviewSamples } from "@/features/review/data";

export const metadata: Metadata = { title: "AI 서류 첨삭" };

export default function ReviewPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="AI 서류 첨삭" />
      <ReviewWorkspace samples={reviewSamples} targetRole={REVIEW_TARGET_ROLE} />
      <div className="flex w-full flex-wrap items-center justify-between gap-4 border-t border-grey-200 pt-5">
        <div className="flex flex-col gap-0.5">
          <p className="text-body font-bold text-grey-900">{reviewNextStep.title}</p>
          <p className="text-small text-grey-600">{reviewNextStep.description}</p>
        </div>
        <div className="flex gap-2">
          <Button href="/diagnosis/result" variant="secondary" size="M">
            직무 진단 결과
          </Button>
          <Button href={`/interview?job=${encodeURIComponent(REVIEW_TARGET_ROLE)}`} size="M">
            이 내용으로 모의면접
          </Button>
        </div>
      </div>
    </PageContainer>
  );
}
