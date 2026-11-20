import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { InterviewHeader } from "@/features/interview/components/InterviewHeader";
import { ReportView } from "@/features/interview/components/ReportView";

export const metadata: Metadata = { title: "면접 리포트" };

export default function InterviewReportPage() {
  return (
    <PageContainer className="gap-7">
      {/* 세션(?session=)을 읽는 화면이라 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<InterviewHeader title="면접 리포트" step={4} />}>
        <ReportView />
      </Suspense>
    </PageContainer>
  );
}
