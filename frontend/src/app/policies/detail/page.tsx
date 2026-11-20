import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PolicyDetail } from "@/features/policies/components/PolicyDetail";

export const metadata: Metadata = { title: "청년 지원 정책" };

/** 정책 상세 `/policies/detail/?id={policyId}`. 정책 ID는 빌드 때 알 수 없어 브라우저에서 `?id=`를 읽는다. */
export default function PolicyDetailPage() {
  return (
    <PageContainer className="gap-5">
      <Suspense fallback={<div className="h-96 w-full" aria-busy />}>
        <PolicyDetail />
      </Suspense>
    </PageContainer>
  );
}
