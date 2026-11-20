import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SavedList } from "@/features/jobs/components/SavedList";

export const metadata: Metadata = { title: "저장한 공고" };

export default function SavedPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="저장한 공고" />
      {/* 오류 안내가 주소를 읽어서 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<div className="h-48 w-full" aria-busy />}>
        <SavedList />
      </Suspense>
    </PageContainer>
  );
}
