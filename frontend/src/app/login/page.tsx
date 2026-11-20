import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { SocialLoginButtons } from "@/features/auth/components/SocialLoginButtons";

export const metadata: Metadata = { title: "로그인" };

export default function LoginPage() {
  return (
    <PageContainer className="items-center">
      <div className="flex w-full max-w-86 flex-col items-center gap-12 pt-16 text-center">
        <div className="flex flex-col items-center gap-6">
          <p className="text-title font-bold text-blue-500">부산커리어</p>
          <h1 className="text-h2 font-medium text-grey-900">
            간편하게 로그인하고
            <br />
            나에게 맞는 공고와 정책을 받아 보세요.
          </h1>
        </div>
        {/* 버튼이 돌아갈 주소(?next=)를 읽어서 Suspense 경계 안에 둔다 */}
        <Suspense fallback={<div className="h-28.5 w-full" aria-busy />}>
          <SocialLoginButtons />
        </Suspense>
        <p className="text-small text-grey-500">이름과 이메일은 받지 않아요. 로그인 확인에만 써요.</p>
      </div>
    </PageContainer>
  );
}
