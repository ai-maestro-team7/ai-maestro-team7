import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { JobTable } from "@/features/jobs/components/JobTable";
import { DATA_AS_OF, jobPostings, RECOMMEND_BASIS } from "@/features/jobs/data";
import { SORT_LABELS, sortJobs } from "@/features/jobs/lib";
import { ContinueList } from "@/features/mentor/components/ContinueList";
import { MentorPanel } from "@/features/mentor/components/MentorPanel";
import { continueItems } from "@/features/mentor/data";
import { PolicyTable } from "@/features/policies/components/PolicyTable";
import { policies } from "@/features/policies/data";

export default function HomePage() {
  const recommendedJobs = sortJobs(jobPostings, "RECOMMENDED").slice(0, 3);

  return (
    <PageContainer className="gap-12">
      <PageHeader title="부산 취업 준비" />

      <div className="flex w-full flex-col gap-12 lg:flex-row lg:items-start">
        <MentorPanel />
        <ContinueList items={continueItems} />
      </div>

      <section aria-labelledby="home-jobs" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-jobs" title="나와 맞는 부산 공고" href="/jobs" />
        <p className="text-small text-grey-600">
          {RECOMMEND_BASIS.role} 프로필 기준 · {SORT_LABELS.RECOMMENDED}
        </p>
        <JobTable jobs={recommendedJobs} asOf={DATA_AS_OF} />
      </section>

      <section aria-labelledby="home-policies" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-policies" title="부산 청년 지원 정책" href="/policies" />
        <PolicyTable policies={policies.slice(0, 3)} />
      </section>
    </PageContainer>
  );
}
