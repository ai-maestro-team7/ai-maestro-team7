import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { DeviceCheck } from "@/features/interview/components/DeviceCheck";
import { InterviewHeader } from "@/features/interview/components/InterviewHeader";

export const metadata: Metadata = { title: "장비 점검" };

export default function InterviewCheckPage() {
  return (
    <PageContainer className="gap-7">
      <InterviewHeader title="장비 점검" step={2} />
      <Suspense fallback={<div className="h-110 w-full" aria-busy />}>
        <DeviceCheck />
      </Suspense>
    </PageContainer>
  );
}
