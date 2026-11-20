import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { RecommendedJobs, RecommendedJobsLoading } from "@/features/jobs/components/RecommendedJobs";
import { MentorPanel } from "@/features/mentor/components/MentorPanel";
import { OpenPolicies } from "@/features/policies/components/OpenPolicies";
import { PolicyTableSkeleton } from "@/features/policies/components/PolicyTable";

export default function HomePage() {
  return (
    <PageContainer className="gap-12">
      <PageHeader title="부산 취업 준비" />

      {/* 메시지 창은 본문 폭(700px)으로 가운데에 둬 한 줄이 너무 길어 보이지 않게 한다 */}
      <div className="mx-auto flex w-full max-w-main">
        <MentorPanel />
      </div>

      {/* 공고·정책은 로그인한 사용자 프로필로 B API에서 읽는다. 오류 안내가 주소(?q=)를 읽어 Suspense 안에 둔다 */}
      <section aria-labelledby="home-jobs" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-jobs" title="나와 맞는 부산 공고" href="/jobs" />
        {/* 대체 화면은 불러오는 중 화면과 같아 바뀔 때 밀리지 않는다 */}
        <Suspense fallback={<RecommendedJobsLoading />}>
          <RecommendedJobs />
        </Suspense>
      </section>

      <section aria-labelledby="home-policies" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-policies" title="부산 청년 지원 정책" href="/policies" />
        <Suspense fallback={<PolicyTableSkeleton rows={3} />}>
          <OpenPolicies />
        </Suspense>
      </section>
    </PageContainer>
  );
}
