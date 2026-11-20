import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { JobDetail } from "@/features/jobs/components/JobDetail";

export const metadata: Metadata = { title: "채용 공고" };

/**
 * 공고 상세 `/jobs/detail/?id={jobPostingId}`.
 * 공고 ID는 B가 매일 새로 모으는 값이라 빌드 때 알 수 없다. 정적 내보내기에서는 `[id]` 경로를 미리 만들 수 없어
 * 한 화면을 내보내고 브라우저에서 `?id=`를 읽어 API를 부른다.
 */
export default function JobDetailPage() {
  return (
    <PageContainer className="gap-5">
      <Suspense fallback={<div className="h-96 w-full" aria-busy />}>
        <JobDetail />
      </Suspense>
    </PageContainer>
  );
}
