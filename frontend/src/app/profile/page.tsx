import type { Metadata } from "next";
import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { ProfileForm } from "@/features/profile/components/ProfileForm";

export const metadata: Metadata = { title: "기본 정보" };

export default function ProfilePage() {
  return (
    <PageContainer className="items-center gap-6">
      <div className="flex w-full max-w-140 flex-col gap-8">
        <PageHeader
          title="기본 정보"
          description="공고 추천과 정책 자격 판정에 쓰는 정보예요. 이름과 연락처는 받지 않아요."
        />
        {/* 폼이 돌아갈 주소(?next=)를 읽어서 Suspense 경계 안에 둔다 */}
        <Suspense fallback={<div className="h-96 w-full" aria-busy />}>
          <ProfileForm />
        </Suspense>
      </div>
    </PageContainer>
  );
}
