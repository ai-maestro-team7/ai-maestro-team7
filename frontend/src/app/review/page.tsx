import type { Metadata } from "next";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { ReviewClient } from "@/features/review/components/ReviewClient";

export const metadata: Metadata = { title: "AI 서류 첨삭" };

export default function ReviewPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="AI 서류 첨삭" />
      <ReviewClient />
    </PageContainer>
  );
}
