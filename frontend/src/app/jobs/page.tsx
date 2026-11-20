import type { Metadata } from "next";
import { OPPORTUNITY_TABS } from "@/components/layout/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SubTabs } from "@/components/ui/SubTabs";
import { PublicJobList } from "@/features/jobs/components/PublicJobList";

export const metadata: Metadata = { title: "채용 공고" };

/** 채용 공고: 로그인 없이 본다. GNB 검색도 여기로 온다 (`?q=`). */
export default function JobsPage() {
  return (
    <PageContainer className="gap-5">
      <PageHeader title="채용 공고" />
      <SubTabs label="채용·정책" items={[...OPPORTUNITY_TABS]} activeKey="jobs" />
      <PublicJobList />
    </PageContainer>
  );
}
