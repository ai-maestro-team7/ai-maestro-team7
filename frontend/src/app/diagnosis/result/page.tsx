import type { Metadata } from "next";
import { PageContainer } from "@/components/layout/PageContainer";
import { Breadcrumb } from "@/components/ui/Breadcrumb";
import { DiagnosisResultClient } from "@/features/diagnosis/components/DiagnosisResultClient";

export const metadata: Metadata = { title: "직무 진단 결과" };

export default function DiagnosisResultPage() {
  return (
    <PageContainer className="gap-6">
      <Breadcrumb items={[{ label: "이력서·직무 진단", href: "/diagnosis" }, { label: "진단 결과" }]} />
      <DiagnosisResultClient />
    </PageContainer>
  );
}
