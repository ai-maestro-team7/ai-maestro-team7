import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { PageContainer, TwoColumn } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Button } from "@/components/ui/Button";
import { DetailSection, DotList, LabeledValue } from "@/components/ui/DetailSection";
import { Panel } from "@/components/ui/Panel";
import { DATA_AS_OF, getJobPosting, jobPostings } from "@/features/jobs/data";
import { deadlineLines, MATCH_LABELS } from "@/features/jobs/lib";
import { cn } from "@/lib/cn";

export const dynamicParams = false;

export function generateStaticParams() {
  return jobPostings.map((job) => ({ id: job.id }));
}

export async function generateMetadata({ params }: PageProps<"/jobs/[id]">): Promise<Metadata> {
  const { id } = await params;
  const job = getJobPosting(id);
  return { title: job ? `${job.company} ${job.title}` : "채용 공고" };
}

export default async function JobDetailPage({ params }: PageProps<"/jobs/[id]">) {
  const { id } = await params;
  const job = getJobPosting(id);
  if (!job) notFound();

  const deadline = deadlineLines(job, DATA_AS_OF);
  const deadlineText = job.deadline ? `마감 ${deadline.main} (${deadline.sub})` : "상시 채용";

  return (
    <PageContainer className="gap-5">
      <Breadcrumb items={[{ label: "채용 공고", href: "/jobs" }, { label: job.company }]} />
      <TwoColumn
        main={
          <article className="flex flex-col">
            <header className="flex flex-col gap-3.5 pb-7">
              <div className="flex items-center gap-2.5">
                <span
                  aria-hidden
                  className="flex size-10 items-center justify-center rounded-control bg-grey-100 text-small font-bold text-grey-600"
                >
                  {job.companyInitial}
                </span>
                <span className="text-body font-bold text-grey-900">{job.company}</span>
                <span className="text-small text-grey-500">{job.companyNote}</span>
              </div>
              <h1 className="text-title font-bold text-grey-900">{job.title}</h1>
              <p className="text-body text-grey-700">
                부산 {job.district} · {job.employmentType} · {job.careerLevel} · {deadlineText}
              </p>
            </header>
            <DetailSection title="주요 업무">
              <DotList items={job.duties} />
            </DetailSection>
            <DetailSection title="요구 역량">
              <DotList items={job.requirements} />
            </DetailSection>
            <DetailSection title="지원 전 확인">
              <p className="text-body text-grey-700">{job.applyNote}</p>
            </DetailSection>
          </article>
        }
        rail={
          <Panel as="aside" aria-label="나와의 적합도" className="flex flex-col gap-4 p-5">
            <div className="flex flex-col">
              <p className="text-small text-grey-600">나와의 적합도</p>
              <p
                className={cn(
                  "text-title font-bold",
                  job.match.level === "GOOD" ? "text-blue-500" : "text-grey-900",
                )}
              >
                {MATCH_LABELS[job.match.level]}
              </p>
            </div>
            <hr className="border-grey-200" />
            <LabeledValue label="맞는 역량">
              <span className="font-medium">{job.matchedSkills.join(" · ")}</span>
            </LabeledValue>
            <LabeledValue label="보완할 역량">{job.gapAdvice}</LabeledValue>
            <div className="flex flex-col gap-2 pt-1.5">
              <Button href={`/interview?job=${encodeURIComponent(job.title)}`} fullWidth>
                이 공고로 모의면접
              </Button>
              <Button href="/diagnosis/result" variant="secondary" fullWidth>
                직무 진단 자세히 보기
              </Button>
            </div>
            <p className="text-small text-grey-600">
              이력서의 기술을 공고 요건과 비교한 결과예요. 합격 확률이 아니에요.
            </p>
          </Panel>
        }
      />
    </PageContainer>
  );
}
