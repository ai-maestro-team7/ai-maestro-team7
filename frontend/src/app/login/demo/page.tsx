import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { LoginForm } from "@/features/auth/components/LoginForm";

export const metadata: Metadata = { title: "시연 계정 로그인", robots: { index: false } };

/** 시연 계정(demo1~demo3) 로그인. 화면 어디에도 링크하지 않는다. 일반 로그인은 `/login/`의 소셜 로그인이다. */
export default function DemoLoginPage() {
  return (
    <PageContainer className="items-center gap-6">
      <div className="flex w-full max-w-100 flex-col gap-6">
        <PageHeader title="시연 계정 로그인" description="팀 시연용 계정으로 들어가요." />
        {/* LoginForm은 돌아갈 주소(?next=)를 읽어서 Suspense 경계 안에 둔다 */}
        <Suspense fallback={<div className="h-64 w-full" aria-busy />}>
          <LoginForm />
        </Suspense>
      </div>
    </PageContainer>
  );
}
