import type { Metadata } from "next";
import { PageContainer } from "@/components/layout/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { RoadmapClient } from "@/features/roadmap/components/RoadmapClient";

export const metadata: Metadata = { title: "학습 로드맵" };

export default function RoadmapPage() {
  return (
    <PageContainer className="gap-7">
      <PageHeader title="학습 로드맵" description="직무 진단의 확인된 격차와 증빙 보완 항목을 기준으로 계획해요." />
      <RoadmapClient />
    </PageContainer>
  );
}
