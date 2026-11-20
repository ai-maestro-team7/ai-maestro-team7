import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SocialCallback } from "@/features/auth/components/SocialCallback";

export const metadata: Metadata = { title: "로그인" };

export default function LoginCallbackPage() {
  return (
    <PageContainer className="items-center gap-6">
      <div className="flex w-full max-w-100 flex-col gap-6">
        <PageHeader title="로그인" />
        {/* SocialCallback은 주소의 code·state를 읽어서 Suspense 경계 안에 둔다 */}
        <Suspense fallback={<div className="h-40 w-full" aria-busy />}>
          <SocialCallback />
        </Suspense>
      </div>
    </PageContainer>
  );
}
