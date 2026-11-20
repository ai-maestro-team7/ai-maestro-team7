import type { Metadata } from "next";
import { PageContainer, TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { NextStepPanel } from "@/components/ui/NextStepPanel";
import { Stats } from "@/components/ui/Stats";
import { FeedbackList } from "@/features/interview/components/FeedbackList";
import { InterviewHeader } from "@/features/interview/components/InterviewHeader";
import { interviewReport as report } from "@/features/interview/data";

export const metadata: Metadata = { title: "면접 리포트" };

export default function InterviewReportPage() {
  return (
    <PageContainer className="gap-7">
      <InterviewHeader title="면접 리포트" step={4} description={report.summary} />
      <TwoColumn
        main={
          <div className="flex flex-col gap-8">
            <div className="flex flex-col gap-2">
              <Stats items={report.stats} />
              <p className="text-small text-grey-600">{report.statsNote}</p>
            </div>
            <FeedbackList items={report.feedback} />
          </div>
        }
        rail={
          <NextStepPanel
            eyebrow="다음 연습에서는"
            title={report.next.title}
            description={report.next.description}
            actions={
              <>
                <Button href="/interview" fullWidth>
                  다시 연습하기
                </Button>
                <Button href="/" variant="secondary" fullWidth>
                  홈으로
                </Button>
              </>
            }
          />
        }
      />
    </PageContainer>
  );
}
