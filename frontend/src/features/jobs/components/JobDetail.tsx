"use client";

import { ExternalLink } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Button } from "@/components/ui/Button";
import { DetailSection, DotList, LabeledValue } from "@/components/ui/DetailSection";
import { Panel } from "@/components/ui/Panel";
import { PageSkeleton } from "@/components/ui/Skeleton";
import { ApiErrorNotice } from "@/features/auth/components/ApiFallback";
import { useUsername } from "@/features/auth/useUsername";
import { policyDetailHref } from "@/features/policies/lib";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { fetchPosting } from "../data";
import {
  asOfDate,
  CAREER_LABELS,
  deadlineLines,
  EMPLOYMENT_LABELS,
  interviewHref,
  jobDetailHref,
  MATCH_LABELS,
  ORG_TYPE_LABELS,
  salaryText,
} from "../lib";
import type { PostingDetailResponse } from "../types";
import { SaveToggle } from "./SaveToggle";

const SOURCE_LABELS: Record<string, string> = {
  WORK24: "고용24",
  ALIO: "잡알리오",
  KLID: "지방공공기관 채용정보",
  WORLDJOB: "월드잡플러스",
  DEMO: "시연용 예시",
};

const CONDITION_MARK = { MET: "충족", NOT_MET: "미충족", UNKNOWN: "확인 필요" } as const;

/** B-04 공고 상세. 정적 내보내기라 공고 ID를 `?id=`로 받는다. */
export function JobDetail() {
  const id = useSearchParams().get("id");
  const username = useUsername();
  const [state, reload] = useApi<PostingDetailResponse>(id ? `${username}|${id}` : null, () => fetchPosting(id ?? ""));
  const title = state.status === "success" ? state.data.posting.title : null;

  useEffect(() => {
    if (title) document.title = `${title} · 부산커리어`;
  }, [title]);

  if (!id) return <NotFound />;
  if (state.status === "loading") return <PageSkeleton label="공고를 불러오는 중" />;
  if (state.status === "error") {
    return state.error.status === 404 ? <NotFound /> : <ApiErrorNotice error={state.error} onRetry={reload} />;
  }
  return <PostingView detail={state.data} />;
}

function NotFound() {
  return (
    <div className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
      <p className="text-body font-bold text-grey-900">공고를 찾을 수 없어요</p>
      <Button href="/jobs" variant="line" size="M">
        채용 공고 목록으로
      </Button>
    </div>
  );
}

function PostingView({ detail }: { detail: PostingDetailResponse }) {
  const { posting } = detail;
  const asOf = asOfDate(detail.dataAsOf);
  const deadline = deadlineLines(posting.closesAt, posting.rolling, asOf);
  const deadlineText = posting.rolling ? "상시 채용" : `마감 ${deadline.main} (${deadline.sub})`;
  const required = posting.requirements.filter((r) => r.kind === "REQUIRED_SKILL").map((r) => r.name);
  const preferred = posting.requirements.filter((r) => r.kind === "PREFERRED_SKILL").map((r) => r.name);
  const meta = [
    posting.workRegion.label,
    ORG_TYPE_LABELS[posting.orgType],
    posting.employmentType && EMPLOYMENT_LABELS[posting.employmentType],
    posting.careerType && CAREER_LABELS[posting.careerType],
    deadlineText,
  ].filter(Boolean);
  const regionalTalent =
    detail.regionalTalent && detail.regionalTalent.status !== "NOT_APPLICABLE"
      ? (detail.regionalTalent.message ?? "지역 조건에 맞을 수 있어요 · 공고문 확인")
      : null;

  return (
    <div className="flex w-full flex-col gap-5">
      <Breadcrumb items={[{ label: "채용 공고", href: "/jobs" }, { label: posting.organization }]} />
      <TwoColumn
        stickyRail
        main={
          <article className="flex flex-col">
            <header className="flex flex-col gap-3.5 pb-7">
              <div className="flex items-center gap-2.5">
                <span className="text-body font-bold text-grey-900">{posting.organization}</span>
                {detail.isSample && <span className="text-small text-grey-500">시연용 예시</span>}
              </div>
              <h1 className="text-title font-bold text-grey-900">{posting.title}</h1>
              <p className="text-body text-grey-700">{meta.join(" · ")}</p>
              {detail.closed && (
                <p role="status" className="text-body font-medium text-red-500">
                  마감된 공고예요.
                </p>
              )}
              {(detail.badges.length > 0 || regionalTalent) && (
                <ul className="flex flex-wrap gap-2">
                  {detail.badges.map((badge) => (
                    <li
                      key={badge.type + badge.label}
                      className="rounded-control bg-grey-100 px-2.5 py-1 text-small text-grey-800"
                    >
                      {badge.label}
                      <span className="text-grey-500">
                        {" "}
                        · {badge.source} {badge.asOf} 기준
                      </span>
                    </li>
                  ))}
                  {regionalTalent && (
                    <li className="rounded-control bg-blue-50 px-2.5 py-1 text-small text-blue-500">{regionalTalent}</li>
                  )}
                </ul>
              )}
            </header>

            <DetailSection title="급여">
              <p className="text-body text-grey-800">{salaryText(posting.salary)}</p>
            </DetailSection>

            <DetailSection title="요구 역량">
              {required.length + preferred.length > 0 ? (
                <div className="flex flex-col gap-3">
                  {required.length > 0 && <LabeledValue label="필수">{required.join(" · ")}</LabeledValue>}
                  {preferred.length > 0 && <LabeledValue label="우대">{preferred.join(" · ")}</LabeledValue>}
                </div>
              ) : (
                <p className="text-body text-grey-700">공고에서 요건을 아직 뽑지 않았어요. 공고 원문에서 확인해 주세요.</p>
              )}
            </DetailSection>

            <DetailSection title="지원 자격">
              {detail.eligibility.conditions.length > 0 ? (
                <DotList
                  items={detail.eligibility.conditions.map(
                    (condition) => `${condition.reason} (${CONDITION_MARK[condition.result]})`,
                  )}
                />
              ) : (
                <p className="text-body text-grey-700">공고 원문에서 자격 조건을 확인해 주세요.</p>
              )}
            </DetailSection>

            {posting.jobDescription && (
              <DetailSection title="공고 내용">
                {/* 공고 원문 텍스트. HTML로 넣지 않고 글자로만 보여준다 */}
                <p className="whitespace-pre-line break-words text-body text-grey-800">{posting.jobDescription}</p>
              </DetailSection>
            )}

            <DetailSection title="출처">
              <p className="text-body text-grey-700">
                {SOURCE_LABELS[posting.source] ?? posting.source}
                {posting.checkedAt && ` · ${formatDateTime(posting.checkedAt)} 확인`}
              </p>
              {posting.officialUrl && (
                <a
                  href={posting.officialUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 text-body font-medium text-blue-500"
                >
                  공고 원문 보기
                  <ExternalLink aria-hidden className="size-4" strokeWidth={2} />
                  <span className="sr-only">(새 창)</span>
                </a>
              )}
            </DetailSection>

            {detail.alternativesPreview.length > 0 && (
              <DetailSection title="같은 일, 부산에서">
                <ul className="flex flex-col gap-2.5">
                  {detail.alternativesPreview.map((alt) => (
                    <li key={alt.jobPostingId}>
                      <Link
                        href={jobDetailHref(alt.jobPostingId)}
                        className="flex flex-col gap-0.5 rounded-card border border-grey-200 px-4 py-3 hover:bg-grey-50"
                      >
                        <span className="text-body font-bold text-grey-900">
                          {alt.organization} · {alt.title}
                        </span>
                        <span className="text-small text-grey-600">
                          {alt.workRegion.label} · {MATCH_LABELS[alt.matchLevel]} · {alt.whyShown}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </DetailSection>
            )}

            {detail.relatedPolicies.length > 0 && (
              <DetailSection title="같이 볼 청년 정책">
                <ul className="flex flex-col gap-2">
                  {detail.relatedPolicies.map((policy) => (
                    <li key={policy.policyId}>
                      <Link href={policyDetailHref(policy.policyId)} className="text-body font-medium text-blue-500">
                        {policy.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </DetailSection>
            )}
          </article>
        }
        rail={
          <Panel as="aside" aria-label="나와의 적합도" className="flex flex-col gap-4 p-5">
            <div className="flex flex-col">
              <div className="flex items-center justify-between gap-2">
                <p className="text-small text-grey-600">나와의 적합도</p>
                <SaveToggle jobPostingId={posting.jobPostingId} jobTitle={`${posting.organization} ${posting.title}`} />
              </div>
              <p
                className={cn(
                  "text-title font-bold",
                  detail.matchLevel === "GOOD" ? "text-blue-500" : "text-grey-900",
                )}
              >
                {detail.matchLevel ? MATCH_LABELS[detail.matchLevel] : "확인 필요"}
              </p>
            </div>
            {detail.facts.length > 0 && (
              <>
                <hr className="border-grey-200" />
                <LabeledValue label="근거">
                  <DotList items={detail.facts} />
                </LabeledValue>
              </>
            )}
            <div className="flex flex-col gap-2 pt-1.5">
              <Button href={interviewHref(posting.title, posting.jobPostingId)} fullWidth>
                이 공고로 모의면접
              </Button>
            </div>
            <p className="text-small text-grey-600">내 프로필을 공고 요건과 비교한 결과예요. 합격 확률이 아니에요.</p>
          </Panel>
        }
      />
    </div>
  );
}
