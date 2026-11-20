import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { RecommendedJobs } from "@/features/jobs/components/RecommendedJobs";
import { ContinueList } from "@/features/mentor/components/ContinueList";
import { continueItems } from "@/features/mentor/data";
import { OpenPolicies } from "@/features/policies/components/OpenPolicies";

export default function HomePage() {
  return (
    <PageContainer className="gap-12">
      <PageHeader title="부산 취업 준비" />

      <div className="flex w-full flex-col gap-12 lg:flex-row lg:items-start">
        {/* 홈의 입구는 채팅 Agent (D-39). 조건·이력서로 공고와 청년정책을 함께 찾는다 */}
        <ChatPanel />
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
