"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { NextStepPanel } from "@/components/ui/NextStepPanel";
import { Panel } from "@/components/ui/Panel";
import { Stats } from "@/components/ui/Stats";
import { TwoColumn } from "@/components/layout/PageContainer";
import { errorMessage, getAnalysis, poll, readFlow, safeExternalUrl } from "@/features/mentoring/api";
import type { AnalysisResponse, RequirementMatch } from "@/features/mentoring/types";
import type { RequirementCheck, RequirementStatus } from "../types";
import { RequirementTable } from "./RequirementTable";

function evidenceText(item: RequirementMatch): string {
  const quote = item.evidence?.find((evidence) => evidence.quotedText)?.quotedText;
  return quote ?? item.question ?? item.reason ?? item.sourceQuote ?? "서류에서 근거를 더 확인해야 해요.";
}

function requirement(item: RequirementMatch, status: RequirementStatus): RequirementCheck {
  return {
    name: item.name ?? (item.kind === "ELIGIBILITY" ? "지원 필수 조건" : "확인 필요"),
    status,
    evidence: evidenceText(item),
  };
}

function eligibilityLabel(status?: string): string {
  if (status === "ELIGIBLE") return "지원 조건 충족";
  if (status === "INELIGIBLE") return "지원 조건 미충족";
  return "지원 조건 확인 필요";
}

export function DiagnosisResultClient() {
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [targetRole, setTargetRole] = useState("데이터 분석");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const flow = readFlow();
      if (!flow) {
        setError("연결된 진단 결과가 없어요. 이력서를 먼저 진단해 주세요.");
        return;
      }
      setTargetRole(flow.targetRole);
      setResult(await poll(() => getAnalysis(flow.analysisId)));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  if (loading) return <p role="status" className="text-body text-grey-700">진단 결과를 불러오고 있어요.</p>;
  if (error || !result) {
    return (
      <Panel className="flex flex-col items-start gap-3 p-6">
        <p role="alert" className="text-body text-grey-800">{error || "진단 결과를 찾지 못했어요."}</p>
        <div className="flex gap-2">
          <Button href="/diagnosis" size="M">이력서 진단하기</Button>
          <Button type="button" size="M" variant="secondary" onClick={() => void load()}>다시 불러오기</Button>
        </div>
      </Panel>
    );
  }

  if (result.status === "REQUIRES_USER_REVIEW") {
    return (
      <Panel className="flex flex-col items-start gap-3 p-6">
        <h1 className="text-h2 font-bold text-grey-900">직무 기준을 한 번 더 확인해야 해요</h1>
        <p className="text-body text-grey-700">{result.nextAction ?? result.reviewReason ?? "분석 기준을 정리한 뒤 다시 확인해 주세요."}</p>
        <div className="flex gap-2">
          <Button href="/diagnosis" size="M" variant="secondary">진단 다시 시작하기</Button>
          <Button type="button" size="M" onClick={() => void load()}>결과 다시 확인</Button>
        </div>
      </Panel>
    );
  }

  const strengths = result.strengths ?? [];
  const partial = result.partialEvidence ?? [];
  const unknown = result.unverifiedSkills ?? [];
  const gaps = result.confirmedGaps ?? [];
  const requirements = [
    ...strengths.map((item) => requirement(item, "MET")),
    ...partial.map((item) => requirement(item, "EVIDENCE")),
    ...unknown.map((item) => requirement(item, "EVIDENCE")),
    ...gaps.map((item) => requirement(item, "GAP")),
  ];
  const fitScore = result.fitScore ?? 0;
  const upperBound = result.potentialUpperBound ?? fitScore;
  const warningMessages = result.warnings?.map((warning) => warning.message) ?? [];

  return (
    <TwoColumn
      main={
        <div className="flex flex-col gap-8">
          <header className="flex flex-col gap-2">
            <h1 className="text-title font-bold text-grey-900">{result.summary || `${targetRole} 직무 진단 결과예요`}</h1>
            <p className="text-body text-grey-700">
              {eligibilityLabel(result.eligibility?.status)} · NCS {result.ncs?.name ?? targetRole}
            </p>
          </header>

          <div className="flex flex-col gap-2">
            <Stats
              items={[
                { label: "서류 기반 일치도", value: fitScore, unit: "점" },
                { label: "가능 범위 상한", value: upperBound, unit: "점" },
                { label: "확인된 강점", value: strengths.length, unit: "개" },
                { label: "확인·보완", value: partial.length + unknown.length + gaps.length, unit: "개" },
              ]}
            />
            <p className="text-small font-medium text-grey-700">적합도는 서류에 나타난 근거의 일치도이며 실제 합격 확률이 아닙니다.</p>
          </div>

          <section aria-labelledby="requirements-title" className="flex flex-col gap-3">
            <h2 id="requirements-title" className="text-h2 font-bold text-grey-900">직무 요구 역량 비교</h2>
            {requirements.length ? (
              <RequirementTable items={requirements} />
            ) : (
              <Panel tone="muted" className="p-5 text-body text-grey-700">확정된 직무 요구사항이 없어 점수를 계산하지 않았어요.</Panel>
            )}
          </section>

          {warningMessages.length > 0 && (
            <Panel as="section" tone="muted" className="p-5" aria-labelledby="analysis-warnings">
              <h2 id="analysis-warnings" className="text-body font-bold text-grey-900">확인할 점</h2>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-grey-700">
                {warningMessages.map((warning) => <li key={warning}>{warning}</li>)}
              </ul>
            </Panel>
          )}

          {(result.sources?.length ?? 0) > 0 && (
            <section aria-labelledby="analysis-sources" className="flex flex-col gap-2">
              <h2 id="analysis-sources" className="text-h3 font-bold text-grey-900">판단 근거와 출처</h2>
              <ul className="space-y-2 text-small text-grey-700">
                {result.sources!.map((source) => {
                  const href = safeExternalUrl(source.sourceUrl);
                  return (
                    <li key={`${source.documentId}-${source.role ?? "source"}`} className="rounded-field border border-grey-200 p-3">
                      <p className="font-bold text-grey-900">{source.documentId}</p>
                      {source.excerpt && <p className="mt-1">{source.excerpt}</p>}
                      <p className="mt-1">확인일 {source.checkedAt ?? result.sourceCheckedAt ?? "확인 필요"}</p>
                      {href && <a href={href} target="_blank" rel="noreferrer" className="text-blue-500">공식 출처 보기</a>}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}
        </div>
      }
      rail={
        <NextStepPanel
          eyebrow="다음에 할 일"
          title={gaps.length ? "확인된 격차부터 학습 계획을 세워 보세요" : "증빙을 보강하고 문장을 다듬어 보세요"}
          description="미확인 역량은 부족으로 단정하지 않아요. 먼저 사실과 근거를 확인해 주세요."
          actions={
            <>
              <Button href="/review" fullWidth>AI 서류 첨삭</Button>
              <Button href="/roadmap" variant="secondary" fullWidth>학습 로드맵 보기</Button>
            </>
          }
        />
      }
    />
  );
}
