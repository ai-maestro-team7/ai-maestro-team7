import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { HomeLogin } from "@/features/auth/components/HomeLogin";
import { RecommendedJobs } from "@/features/jobs/components/RecommendedJobs";
import { ContinueList } from "@/features/mentor/components/ContinueList";
import { MentorPanel } from "@/features/mentor/components/MentorPanel";
import { continueItems } from "@/features/mentor/data";
import { OpenPolicies } from "@/features/policies/components/OpenPolicies";

export default function HomePage() {
  return (
    <PageContainer className="gap-12">
      <PageHeader title="부산 취업 준비" />

      {/* 로그인 전에만 보인다. 소셜 로그인 버튼이 주소(?next=)를 읽어 Suspense 안에 둔다 */}
      <Suspense fallback={null}>
        <HomeLogin />
      </Suspense>

      <div className="flex w-full flex-col gap-12 lg:flex-row lg:items-start">
        <MentorPanel />
        <ContinueList items={continueItems} />
      </div>

      {/* 공고·정책은 로그인한 사용자 프로필로 B API에서 읽는다. 오류 안내가 주소(?q=)를 읽어 Suspense 안에 둔다 */}
      <section aria-labelledby="home-jobs" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-jobs" title="나와 맞는 부산 공고" href="/jobs" />
        <Suspense fallback={<div className="h-48 w-full" aria-busy />}>
          <RecommendedJobs />
        </Suspense>
      </section>

      <section aria-labelledby="home-policies" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-policies" title="부산 청년 지원 정책" href="/policies" />
        <Suspense fallback={<div className="h-48 w-full" aria-busy />}>
          <OpenPolicies />
        </Suspense>
      </section>
    </PageContainer>
  );
}
