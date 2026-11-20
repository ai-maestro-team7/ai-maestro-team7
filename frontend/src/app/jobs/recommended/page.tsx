import type { Metadata } from "next";
import { OPPORTUNITY_TABS } from "@/components/layout/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { ArrowLink } from "@/components/ui/ArrowLink";
import { PageHeader } from "@/components/ui/PageHeader";
import { SubTabs } from "@/components/ui/SubTabs";
import { LoginGate } from "@/features/auth/components/LoginGate";
import { JobList } from "@/features/jobs/components/JobList";

export const metadata: Metadata = { title: "맞춤형 공고" };

/** 맞춤형 공고 (B-03 맞춤 피드): 로그인해야 본다. 홈의 "지역인재 전형 공고 보기"는 `?talent=1`로 들어온다. */
export default function RecommendedJobsPage() {
  return (
    <PageContainer className="gap-5">
      <PageHeader title="맞춤형 공고" />
      <SubTabs label="채용·정책" items={[...OPPORTUNITY_TABS]} activeKey="recommended" />
      <LoginGate
        title="로그인하면 내 프로필에 맞춘 공고를 볼 수 있어요"
        description="희망 직무와 경력을 공고 요건과 비교한 적합도, 부산에서 비슷한 공고 수를 함께 보여 드려요."
      >
        {/* 검색어(?q=)를 읽는 부분의 Suspense 경계는 JobList 안에 있다. 필터·정렬 줄은 처음부터 그린다 */}
        <JobList />
        <div className="flex flex-wrap items-center gap-2.5">
          <p className="text-small text-grey-700">지원할 공고를 골랐다면</p>
          <ArrowLink href="/interview" tone="blue">
            AI 모의면접으로 연습하기
          </ArrowLink>
        </div>
      </LoginGate>
    </PageContainer>
  );
}
