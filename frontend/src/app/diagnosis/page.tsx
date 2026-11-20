import type { Metadata } from "next";
import { PageContainer, TwoColumn } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { DiagnosisForm } from "@/features/diagnosis/components/DiagnosisForm";
import { diagnosisGuide } from "@/features/diagnosis/data";

export const metadata: Metadata = { title: "이력서·직무 진단" };

export default function DiagnosisPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="이력서·직무 진단" />
      <TwoColumn
        main={<DiagnosisForm />}
        rail={
          <aside aria-labelledby="diagnosis-guide" className="flex flex-col gap-1.5">
            <h2 id="diagnosis-guide" className="text-h3 font-bold text-grey-900">
              진단하면 알 수 있어요
            </h2>
            <ul className="flex flex-col">
              {diagnosisGuide.map((item) => (
                <li key={item.title} className="flex flex-col gap-0.5 border-b border-grey-200 py-3 last:border-b-0">
                  <p className="text-body font-bold text-grey-900">{item.title}</p>
                  <p className="text-small text-grey-600">{item.description}</p>
                </li>
              ))}
            </ul>
          </aside>
        }
      />
    </PageContainer>
  );
}
