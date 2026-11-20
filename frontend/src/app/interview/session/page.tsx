import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { InterviewHeader } from "@/features/interview/components/InterviewHeader";
import { InterviewSession } from "@/features/interview/components/InterviewSession";

export const metadata: Metadata = { title: "AI 모의면접 진행" };

export default function InterviewSessionPage() {
  return (
    <PageContainer className="gap-7">
      {/* 진행 방식(?mode=)을 읽는 화면이라 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<InterviewHeader title="AI 모의면접" step={3} />}>
        <InterviewSession />
      </Suspense>
    </PageContainer>
  );
}
