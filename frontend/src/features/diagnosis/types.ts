import type { StatItem } from "@/components/ui/Stats";

/** 요구 역량 상태. 서류에 없는 역량은 "부족"이 아니라 확인·보완 대상으로 다룬다 (제품 원칙 5). */
export type RequirementStatus = "MET" | "GAP" | "EVIDENCE";

export type RequirementCheck = {
  name: string;
  status: RequirementStatus;
  evidence: string;
};

export type DiagnosisGuideItem = { title: string; description: string };

export type DiagnosisResult = {
  targetRole: string;
  headline: string;
  summary: string;
  stats: StatItem[];
  statsNote: string;
  requirements: RequirementCheck[];
  nextAction: { title: string; description: string };
};

export type DiagnosisInputTab = "PDF" | "TEXT";
