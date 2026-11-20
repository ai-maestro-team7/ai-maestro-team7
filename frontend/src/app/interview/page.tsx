import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { InterviewHeader } from "@/features/interview/components/InterviewHeader";
import { SetupForm } from "@/features/interview/components/SetupForm";

export const metadata: Metadata = { title: "AI 모의면접" };

export default function InterviewSetupPage() {
  return (
    <PageContainer className="gap-7">
      <InterviewHeader title="AI 모의면접" step={1} />
      {/* SetupForm은 공고·첨삭 화면에서 넘긴 직무(?job=)를 읽어서 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<div className="h-160 w-full" aria-busy />}>
        <SetupForm />
      </Suspense>
    </PageContainer>
  );
}
