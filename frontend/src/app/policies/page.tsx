import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import { OPPORTUNITY_TABS } from "@/components/layout/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { SubTabs } from "@/components/ui/SubTabs";
import { PolicyTable } from "@/features/policies/components/PolicyTable";
import { featuredPolicy, policies } from "@/features/policies/data";

export const metadata: Metadata = { title: "청년 지원 정책" };

export default function PoliciesPage() {
  const featured = featuredPolicy.policy;
  return (
    <PageContainer className="gap-5">
      <PageHeader title="청년 지원 정책" />
      <SubTabs label="채용·정책" items={[...OPPORTUNITY_TABS]} activeKey="policies" />
      <div className="flex w-full flex-col gap-2.5">
        <p className="flex flex-wrap gap-1.5 text-small">
          <span className="font-bold text-grey-900">{policies.length}건</span>
          <span className="text-grey-600">정책 유형 예시예요. 신청 자격과 일정은 정책 상세에서 확인해 주세요.</span>
        </p>
        <PolicyTable policies={policies} />
      </div>
      <Panel className="flex w-full flex-wrap items-center justify-between gap-4 px-5 py-4.5">
        <div className="flex flex-col gap-1">
          <p className="text-body font-bold text-grey-900">신청 전에 확인하세요</p>
          <p className="text-small text-grey-700">정책마다 거주지, 연령, 구직 상태와 제출 서류가 달라요.</p>
          <p className="flex items-center gap-1.5 text-small">
            <span className="text-grey-600">공식 정보</span>
            <a
              href={featured.officialSource.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-medium text-blue-500"
            >
              {featured.officialSource.label}
              <ExternalLink aria-hidden className="size-3.5" strokeWidth={2} />
              <span className="sr-only">(새 창)</span>
            </a>
          </p>
        </div>
        <Button href={`/policies/${featured.id}`} variant="line" size="M">
          {featuredPolicy.linkLabel}
        </Button>
      </Panel>
    </PageContainer>
  );
}
