import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import { OPPORTUNITY_TABS } from "@/components/layout/navigation";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { Panel } from "@/components/ui/Panel";
import { SubTabs } from "@/components/ui/SubTabs";
import { LoginGate } from "@/features/auth/components/LoginGate";
import { PolicyList } from "@/features/policies/components/PolicyList";
import { BUSAN_YOUTH_PLATFORM } from "@/features/policies/data";

export const metadata: Metadata = { title: "청년 지원 정책" };

export default function PoliciesPage() {
  return (
    <PageContainer className="gap-5">
      <PageHeader title="청년 지원 정책" />
      <SubTabs label="채용·정책" items={[...OPPORTUNITY_TABS]} activeKey="policies" />
      <LoginGate
        title="로그인하면 받을 수 있는 청년 지원 정책을 볼 수 있어요"
        description="거주지, 나이, 구직 상태를 내 기본 정보로 확인해서 신청할 수 있는 정책부터 보여 드려요."
      >
        <PolicyList />
        <Panel className="flex w-full flex-col gap-1 px-5 py-4.5">
          <p className="text-body font-bold text-grey-900">신청 전에 확인하세요</p>
          <p className="text-small text-grey-700">
            정책마다 거주지, 연령, 구직 상태와 제출 서류가 달라요. 자격 판정은 내 기본 프로필로 계산한 결과예요.
          </p>
          <p className="flex items-center gap-1.5 text-small">
            <span className="text-grey-600">공식 정보</span>
            <a
              href={BUSAN_YOUTH_PLATFORM.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 font-medium text-blue-500"
            >
              {BUSAN_YOUTH_PLATFORM.label}
              <ExternalLink aria-hidden className="size-3.5" strokeWidth={2} />
              <span className="sr-only">(새 창)</span>
            </a>
          </p>
        </Panel>
      </LoginGate>
    </PageContainer>
  );
}
