import type { Metadata } from "next";
import { OPPORTUNITY_TABS } from "@/components/layout/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { ArrowLink } from "@/components/ui/ArrowLink";
import { PageHeader } from "@/components/ui/PageHeader";
import { SubTabs } from "@/components/ui/SubTabs";
import { JobList } from "@/features/jobs/components/JobList";

export const metadata: Metadata = { title: "채용 공고" };

export default function JobsPage() {
  return (
    <PageContainer className="gap-5">
      <PageHeader title="채용 공고" />
      <SubTabs label="채용·정책" items={[...OPPORTUNITY_TABS]} activeKey="jobs" />
      {/* 검색어(?q=)를 읽는 부분의 Suspense 경계는 JobList 안에 있다. 필터·정렬 줄은 처음부터 그린다 */}
      <JobList />
      <div className="flex flex-wrap items-center gap-2.5">
        <p className="text-small text-grey-700">지원할 공고를 골랐다면</p>
        <ArrowLink href="/interview" tone="blue">
          AI 모의면접으로 연습하기
        </ArrowLink>
      </div>
    </PageContainer>
  );
}
