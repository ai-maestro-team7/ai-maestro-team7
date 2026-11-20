"use client";

import { useSearchParams } from "next/navigation";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { NextStepPanel } from "@/components/ui/NextStepPanel";
import { ApiErrorNotice, ApiLoading } from "@/features/auth/components/ApiFallback";
import { cn } from "@/lib/cn";
import { useInterviewStatus } from "../hooks/useInterviewStatus";
import { interviewQuery, modeLabel, parseMode, parseSessionId, readJob, stageMessage, typeLabel } from "../lib";
import type { AreaScore, InterviewReport } from "../types";
import { FeedbackList } from "./FeedbackList";
import { InterviewHeader } from "./InterviewHeader";
import { MissingSession } from "./MissingSession";

/** 영역 점수 한 칸. 측정하지 않은 영역은 점수 대신 "미측정"을 보여준다. */
function ScoreCell({ label, score, note, first }: { label: string; score: number | null; note?: string | null; first?: boolean }) {
  return (
    <div className={cn("flex flex-col gap-0.5 px-6", !first && "sm:border-l sm:border-grey-200")}>
      <dt className="text-small text-grey-600">{label}</dt>
      <dd className="flex items-baseline gap-0.75">
        {score !== null ? (
          <>
            <span className="text-num font-bold text-grey-900">{score}</span>
            <span className="text-body font-medium text-grey-700">점</span>
          </>
        ) : (
          <span className="text-h2 font-bold text-grey-500">미측정</span>
        )}
        {note && <span className="ml-1.5 text-small font-medium text-grey-700">{note}</span>}
      </dd>
    </div>
  );
}

function area(value: AreaScore | undefined): number | null {
  return value?.score ?? null;
}

/** 다음에 할 일: 점수가 가장 낮은 영역으로 안내한다. 점수는 서버 값이고 문장만 화면에서 고른다. */
function nextStep(report: InterviewReport): { title: string; description: string } {
  const areas = [
    { score: area(report.areas.content), title: "답변 내용을 더 구체적으로 준비해 보세요", description: "질문별 보완할 점을 보고 상황, 행동, 결과가 드러나게 답변을 다듬어 보세요." },
    { score: area(report.areas.delivery), title: "말하는 속도와 침묵을 점검해 보세요", description: "질문별 말 속도와 긴 침묵 횟수를 보고 같은 질문으로 한 번 더 연습해 보세요." },
    { score: area(report.areas.attitude), title: "답변할 때 시선을 확인해 보세요", description: "핵심을 말할 때 카메라 가까이를 바라보는 연습을 해 보세요." },
  ].filter((item): item is { score: number; title: string; description: string } => item.score !== null);
  if (areas.length === 0) return { title: "한 번 더 연습해 보세요", description: "답변이 인식되지 않아 평가하지 못했어요. 마이크를 확인하고 다시 연습해 보세요." };
  return areas.reduce((lowest, item) => (item.score < lowest.score ? item : lowest));
}

/** 모의면접 4단계: 리포트. `/status`의 `report`를 그대로 보여준다. 아직 만드는 중이면 기다린다. */
export function ReportView() {
  const params = useSearchParams();
  const sessionId = parseSessionId(params.get("session"));
  const job = readJob(params.get("job"));
  const mode = parseMode(params.get("mode"));
  const { status, error } = useInterviewStatus(sessionId);

  if (!sessionId) {
    return (
      <>
        <InterviewHeader title="면접 리포트" step={4} />
        <MissingSession />
      </>
    );
  }
  if (error) {
    return (
      <>
        <InterviewHeader title="면접 리포트" step={4} />
        <ApiErrorNotice error={error} />
      </>
    );
  }
  if (status?.status === "FAILED") {
    return (
      <>
        <InterviewHeader title="면접 리포트" step={4} />
        <div role="alert" className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
          <p className="text-body font-bold text-grey-900">{status.error?.message ?? "리포트를 만들지 못했어요."}</p>
          <Button href={`/interview?${interviewQuery({ job, mode })}`} size="M">
            다시 연습하기
          </Button>
        </div>
      </>
    );
  }
  const report = status?.report;
  if (!report) {
    return (
      <>
        <InterviewHeader title="면접 리포트" step={4} />
        <ApiLoading label={status ? stageMessage(status.stage) : "불러오는 중"} />
      </>
    );
  }

  const next = nextStep(report);
  const summary = [report.job, typeLabel(report.interviewType), modeLabel(mode), report.interviewDate].filter(Boolean).join(" · ");

  return (
    <>
      <InterviewHeader title="면접 리포트" step={4} description={summary} />
      <TwoColumn
        main={
          <div className="flex flex-col gap-8">
            <div className="flex flex-col gap-2">
              <dl className="grid grid-cols-2 gap-y-4 rounded-card border border-grey-200 py-5 sm:grid-cols-4">
                <ScoreCell label="종합" score={report.totalScore} note={report.grade} first />
                <ScoreCell label="내용" score={area(report.areas.content)} />
                <ScoreCell label="전달력" score={area(report.areas.delivery)} />
                <ScoreCell label="시선·자세" score={area(report.areas.attitude)} />
              </dl>
              <p className="text-small text-grey-600">{report.weightBasis}</p>
              {report.notMeasuredMessages.map((message) => (
                <p key={message} className="text-small text-grey-600">
                  {message}
                </p>
              ))}
              <p className="text-small text-grey-600">{report.notice}</p>
            </div>
            <FeedbackList items={report.questions} />
          </div>
        }
        rail={
          <NextStepPanel
            eyebrow="다음 연습에서는"
            title={next.title}
            description={next.description}
            actions={
              <Button href={`/interview?${interviewQuery({ job, mode })}`} fullWidth>
                다시 연습하기
              </Button>
            }
          />
        }
      />
    </>
  );
}
