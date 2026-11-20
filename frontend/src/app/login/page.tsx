import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { LoginForm } from "@/features/auth/components/LoginForm";
import { SocialLoginButtons } from "@/features/auth/components/SocialLoginButtons";

export const metadata: Metadata = { title: "로그인" };

export default function LoginPage() {
  return (
    <PageContainer className="items-center gap-6">
      <div className="flex w-full max-w-100 flex-col gap-6">
        <PageHeader title="로그인" description="시연 계정으로 로그인하면 내 프로필에 맞춘 공고와 정책을 볼 수 있어요." />
        {/* LoginForm은 돌아갈 주소(?next=)를 읽어서 Suspense 경계 안에 둔다 */}
        <Suspense fallback={<div className="h-64 w-full" aria-busy />}>
          <LoginForm />
        </Suspense>
        <Suspense fallback={null}>
          <SocialLoginButtons />
        </Suspense>
        <p className="text-small text-grey-600">회원가입은 없어요. 계정은 팀 관리자가 만들어요.</p>
      </div>
    </PageContainer>
  );
}
