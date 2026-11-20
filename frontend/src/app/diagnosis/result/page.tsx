import type { Metadata } from "next";
import { PageContainer, TwoColumn } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { Button } from "@/components/ui/Button";
import { NextStepPanel } from "@/components/ui/NextStepPanel";
import { PageHeader } from "@/components/ui/PageHeader";
import { Stats } from "@/components/ui/Stats";
import { RequirementTable } from "@/features/diagnosis/components/RequirementTable";
import { diagnosisResult as result } from "@/features/diagnosis/data";

export const metadata: Metadata = { title: "직무 진단 결과" };

export default function DiagnosisResultPage() {
  return (
    <PageContainer className="gap-6">
      <Breadcrumb items={[{ label: "이력서·직무 진단", href: "/diagnosis" }, { label: "진단 결과" }]} />
      <PageHeader title={result.headline} description={result.summary} />
      <TwoColumn
        main={
          <div className="flex flex-col gap-8">
            <div className="flex flex-col gap-2">
              <Stats items={result.stats} />
              <p className="text-small text-grey-600">{result.statsNote}</p>
            </div>
            <section aria-labelledby="requirements-title" className="flex flex-col gap-3">
              <h2 id="requirements-title" className="text-h2 font-bold text-grey-900">
                직무 요구 역량 비교
              </h2>
              <RequirementTable items={result.requirements} />
            </section>
          </div>
        }
        rail={
          <NextStepPanel
            eyebrow="다음에 할 일"
            title={result.nextAction.title}
            description={result.nextAction.description}
            actions={
              <>
                <Button href="/roadmap" fullWidth>
                  학습 로드맵 보기
                </Button>
                <Button href="/jobs" variant="secondary" fullWidth>
                  부산 맞춤 채용 보기
                </Button>
              </>
            }
          />
        }
      />
    </PageContainer>
  );
}
