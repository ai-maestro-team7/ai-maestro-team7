import { ExternalLink } from "lucide-react";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageContainer, TwoColumn } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Button } from "@/components/ui/Button";
import { LabeledValue } from "@/components/ui/DetailSection";
import { Panel } from "@/components/ui/Panel";
import { StatusDot } from "@/components/ui/StatusDot";
import { PolicyChecklist } from "@/features/policies/components/PolicyChecklist";
import { getPolicy, policies } from "@/features/policies/data";
import { POLICY_STATUS } from "@/features/policies/lib";

export const dynamicParams = false;

export function generateStaticParams() {
  return policies.map((policy) => ({ id: policy.id }));
}

export async function generateMetadata({ params }: PageProps<"/policies/[id]">): Promise<Metadata> {
  const { id } = await params;
  return { title: getPolicy(id)?.name ?? "청년 지원 정책" };
}

export default async function PolicyDetailPage({ params }: PageProps<"/policies/[id]">) {
  const { id } = await params;
  const policy = getPolicy(id);
  if (!policy) notFound();
  const status = POLICY_STATUS[policy.status];

  return (
    <PageContainer className="gap-5">
      <Breadcrumb items={[{ label: "청년 지원 정책", href: "/policies" }, { label: policy.name }]} />
      <TwoColumn
        main={
          <article className="flex flex-col gap-4">
            <header className="flex flex-col gap-2.5 pb-3">
              <h1 className="text-title font-bold text-grey-900">{policy.name}</h1>
              <p className="text-body text-grey-700">{policy.summary}</p>
            </header>
            <PolicyChecklist items={policy.checklist} />
            <p className="text-small text-grey-600">{policy.note}</p>
          </article>
        }
        rail={
          <Panel as="aside" aria-label="정책 요약" className="flex flex-col gap-4 p-5">
            <StatusDot tone={status.tone} label={status.detailLabel} />
            <LabeledValue label="추천한 이유">{policy.reason}</LabeledValue>
            <hr className="border-grey-200" />
            <a
              href={policy.officialSource.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between gap-3"
            >
              <span className="flex flex-col gap-0.5">
                <span className="text-small text-grey-600">공식 정보 확인처</span>
                <span className="text-body font-medium text-blue-500">{policy.officialSource.label}</span>
              </span>
              <ExternalLink aria-hidden className="size-4 text-blue-500" strokeWidth={2} />
              <span className="sr-only">(새 창)</span>
            </a>
            <Button href="/policies" variant="secondary" fullWidth>
              다른 지원 정책 보기
            </Button>
          </Panel>
        }
      />
    </PageContainer>
  );
}
