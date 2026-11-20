"use client";

import { ExternalLink } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Button } from "@/components/ui/Button";
import { DetailSection, DotList, LabeledValue } from "@/components/ui/DetailSection";
import { Panel } from "@/components/ui/Panel";
import { StatusDot } from "@/components/ui/StatusDot";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { fetchPolicy } from "../data";
import { applyPeriod, POLICY_BUCKETS, POLICY_STATUS, SELECTION_LABELS } from "../lib";
import type { PolicyCard, PolicyDetailResponse } from "../types";
import { PolicyChecklist } from "./PolicyChecklist";

const SOURCE_LABELS: Record<string, string> = {
  YOUTHCENTER: "온통청년",
  BUSAN_SEED: "부산 청년정책 정리 자료",
  BUSAN_CITY: "부산광역시 청년지원프로그램",
};

/** 정책 상세. 정적 내보내기라 정책 ID를 `?id=`로 받는다. */
export function PolicyDetail() {
  const id = useSearchParams().get("id");
  const username = useUsername();
  const [state, reload] = useApi<PolicyDetailResponse>(id ? `${username}|${id}` : null, () => fetchPolicy(id ?? ""));
  const title = state.status === "success" ? state.data.policy.title : null;

  useEffect(() => {
    if (title) document.title = `${title} · 부산커리어`;
  }, [title]);

  if (!id) return <NotFound />;
  if (state.status === "loading") return <PageSkeleton label="정책을 불러오는 중" />;
  if (state.status === "error") {
    return state.error.status === 404 ? <NotFound /> : <ApiErrorNotice error={state.error} onRetry={reload} />;
  }
  return <PolicyView policy={state.data.policy} />;
}

function NotFound() {
  return (
    <div className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
      <p className="text-body font-bold text-grey-900">정책을 찾을 수 없어요</p>
      <Button href="/policies" variant="line" size="M">
        청년 지원 정책 목록으로
      </Button>
    </div>
  );
}

function PolicyView({ policy }: { policy: PolicyCard }) {
  const status = POLICY_STATUS[policy.eligibility.status];
  const bucket = POLICY_BUCKETS.find((b) => b.value === policy.bucket)?.label;
  const source = SOURCE_LABELS[policy.source] ?? policy.source;

  return (
    <div className="flex w-full flex-col gap-5">
      <Breadcrumb items={[{ label: "청년 지원 정책", href: "/policies" }, { label: policy.title }]} />
      <TwoColumn
        main={
          <article className="flex flex-col">
            <header className="flex flex-col gap-2.5 pb-7">
              <h1 className="text-title font-bold text-grey-900">{policy.title}</h1>
              <p className="text-body text-grey-700">{[bucket, policy.category].filter(Boolean).join(" · ")}</p>
            </header>
            {policy.summary && (
              <DetailSection title="정책 내용">
                {/* 원문 텍스트. HTML로 넣지 않고 글자로만 보여준다 */}
                <p className="whitespace-pre-line break-words text-body text-grey-800">{policy.summary}</p>
              </DetailSection>
            )}
            {policy.benefit?.text && policy.benefit.text !== policy.summary && (
              <DetailSection title="지원 내용">
                <p className="whitespace-pre-line break-words text-body text-grey-800">{policy.benefit.text}</p>
              </DetailSection>
            )}
            <DetailSection title="신청">
              <div className="flex flex-col gap-3">
                <LabeledValue label="신청 기간">{applyPeriod(policy.application)}</LabeledValue>
                {policy.application.selection && (
                  <LabeledValue label="선정 방식">{SELECTION_LABELS[policy.application.selection]}</LabeledValue>
                )}
              </div>
            </DetailSection>
            {policy.checklist && policy.checklist.length > 0 && <PolicyChecklist items={policy.checklist} />}
          </article>
        }
        rail={
          <Panel as="aside" aria-label="정책 요약" className="flex flex-col gap-4 p-5">
            <StatusDot tone={status.tone} label={status.detailLabel} />
            {policy.eligibility.reasons.length > 0 && (
              <LabeledValue label="판정 근거">
                <DotList items={policy.eligibility.reasons} />
              </LabeledValue>
            )}
            {policy.eligibility.manualChecks.length > 0 && (
              <LabeledValue label="직접 확인할 조건">
                <DotList items={policy.eligibility.manualChecks} />
              </LabeledValue>
            )}
            <hr className="border-grey-200" />
            {policy.url ? (
              <a href={policy.url} target="_blank" rel="noopener noreferrer" className="flex items-center justify-between gap-3">
                <span className="flex flex-col gap-0.5">
                  <span className="text-small text-grey-600">공식 정보 확인처</span>
                  <span className="text-body font-medium text-blue-500">{source}</span>
                </span>
                <ExternalLink aria-hidden className="size-4 text-blue-500" strokeWidth={2} />
                <span className="sr-only">(새 창)</span>
              </a>
            ) : (
              <LabeledValue label="출처">{source}</LabeledValue>
            )}
            {policy.asOf && <p className="text-small text-grey-600">{formatDate(policy.asOf)} 기준 정보예요.</p>}
            <Button href="/policies" variant="secondary" fullWidth>
              다른 지원 정책 보기
            </Button>
          </Panel>
        }
      />
    </div>
  );
}
