import { PageHeader } from "@/components/ui/PageHeader";
import { type StepNumber, Steps } from "@/components/ui/Steps";

/** 모의면접 화면 제목 줄 (제목 + 오른쪽 Steps). */
export function InterviewHeader({
  title,
  step,
  description,
}: {
  title: string;
  step: StepNumber;
  description?: string;
}) {
  return <PageHeader title={title} description={description} aside={<Steps current={step} />} />;
}
