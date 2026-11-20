import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { ResumeReview } from "@/features/mentoring/components/ResumeReview";

export const metadata: Metadata = { title: "이력서 내용 확인" };

export default function ResumeReviewPage() {
  return (
    <PageContainer className="items-center py-8">
      <Suspense fallback={<p aria-busy>이력서 내용을 불러오고 있어요.</p>}>
        <ResumeReview />
      </Suspense>
    </PageContainer>
  );
}
