"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { TextArea } from "@/components/ui/TextArea";
import { answerGuide, interviewDefaults, interviewQuestions } from "../data";
import { interviewQuery, modeLabel, parseMode, readJob } from "../lib";
import type { InterviewMode, InterviewQuestion } from "../types";
import { CameraPreview } from "./CameraPreview";
import { InterviewHeader } from "./InterviewHeader";
import { Recorder } from "./Recorder";

type Phase = "main" | "followUp";

/**
 * 모의면접 3단계: 면접. 음성 방식은 질문 → 추가 질문(질문당 최대 1개) → 다음 질문,
 * 텍스트 방식은 질문 → 다음 질문 순서로 진행한다. 마지막 질문 뒤에는 리포트로 이동한다.
 */
export function InterviewSession() {
  const router = useRouter();
  const params = useSearchParams();
  const job = readJob(params.get("job"));
  const mode = parseMode(params.get("mode"));

  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<Phase>("main");
  const [answers, setAnswers] = useState<string[]>(() => interviewQuestions.map((q) => q.sampleAnswer));

  const question = interviewQuestions[index];
  const total = interviewQuestions.length;
  const isVoice = mode !== "text";
  const answer = answers[index];

  function goNext() {
    if (index + 1 >= total) {
      router.push(`/interview/report?${interviewQuery({ job, mode })}`);
      return;
    }
    setIndex(index + 1);
    setPhase("main");
  }

  function handleComplete() {
    if (isVoice && phase === "main") {
      setPhase("followUp");
      return;
    }
    goNext();
  }

  const showFollowUp = phase === "followUp";
  const asked = showFollowUp ? question.followUp : question;
  const progressLabel = `질문 ${index + 1} / ${total}${showFollowUp ? " · 추가 질문" : ""}`;
  const completeLabel = isVoice && !showFollowUp ? "답변 완료하고 추가 질문 받기" : "답변 완료하고 다음 질문으로";
  const canComplete = isVoice || answer.trim().length > 0;

  return (
    <>
      <InterviewHeader
        title="AI 모의면접"
        step={3}
        description={`${job} · ${interviewDefaults.interviewType} · ${modeLabel(mode)}`}
      />
      <TwoColumn
        main={
          <div className="flex flex-col gap-7">
            <ProgressBar label={progressLabel} value={(index + 1) / total} />
            <section aria-labelledby="interview-question" aria-live="polite" className="flex flex-col gap-2.5">
              <p className="text-small font-bold text-grey-600">AI 면접관</p>
              <h2 id="interview-question" className="text-question font-bold text-grey-900">
                {asked.question}
              </h2>
              <p className="text-body text-grey-700">{asked.hint}</p>
            </section>

            {showFollowUp ? (
              <Panel tone="muted" className="flex flex-col gap-1.5 px-4.5 py-4">
                <p className="text-small text-grey-600">예시 답변</p>
                <p className="text-body text-grey-900">{question.followUp.sampleAnswer}</p>
              </Panel>
            ) : isVoice ? (
              <Recorder key={question.id} />
            ) : (
              <TextArea
                id={`answer-${question.id}`}
                label="내 답변"
                value={answer}
                onChange={(event) =>
                  setAnswers((prev) => prev.map((value, i) => (i === index ? event.target.value : value)))
                }
                counterSuffix="· 예시"
                rows={2}
              />
            )}

            <div className="flex items-center justify-between gap-4">
              <Button href="/interview" variant="textMuted">
                면접 종료
              </Button>
              <Button onClick={handleComplete} disabled={!canComplete}>
                {completeLabel}
              </Button>
            </div>
          </div>
        }
        rail={<SessionRail mode={mode} question={question} showFollowUp={showFollowUp} />}
      />
    </>
  );
}

function SessionRail({
  mode,
  question,
  showFollowUp,
}: {
  mode: InterviewMode;
  question: InterviewQuestion;
  showFollowUp: boolean;
}) {
  if (showFollowUp) {
    return (
      <Panel as="aside" aria-labelledby="why-question" className="flex flex-col gap-2 p-5">
        <h2 id="why-question" className="text-h3 font-bold text-grey-900">
          왜 이 질문인가요?
        </h2>
        <p className="text-body text-grey-700">{question.followUp.reason}</p>
      </Panel>
    );
  }

  if (mode === "text") {
    return (
      <aside aria-labelledby="answer-guide" className="flex flex-col gap-3">
        <h2 id="answer-guide" className="text-h3 font-bold text-grey-900">
          답변 가이드
        </h2>
        <ol className="flex flex-col">
          {answerGuide.map((item, i) => (
            <li key={item.title} className="flex gap-2.5 border-b border-grey-200 py-3 last:border-b-0">
              <span className="text-body font-bold text-grey-500">{i + 1}</span>
              <span className="flex flex-col gap-0.5">
                <span className="text-body font-bold text-grey-900">{item.title}</span>
                <span className="text-small text-grey-600">{item.description}</span>
              </span>
            </li>
          ))}
        </ol>
        <p className="text-small text-grey-600">답변은 예시 상태로 진행돼요.</p>
      </aside>
    );
  }

  if (mode === "voice") {
    return (
      <Panel as="aside" tone="muted" className="flex flex-col gap-1 p-5">
        <p className="text-body font-bold text-grey-900">카메라 없이 진행 중이에요</p>
        <p className="text-small text-grey-600">답변 내용과 전달력만 확인해요. 답변은 예시 상태로 진행돼요.</p>
      </Panel>
    );
  }

  return (
    <aside aria-label="카메라" className="flex flex-col gap-3">
      <CameraPreview size="S" label="카메라 미리보기 자리 (시연 화면)" />
      <p className="text-small font-medium text-grey-900">시선이 가운데 있어요 · 예시</p>
      <p className="text-small text-grey-600">시선과 고개 움직임은 연습용 지표예요. 답변은 예시 상태로 진행돼요.</p>
    </aside>
  );
}
