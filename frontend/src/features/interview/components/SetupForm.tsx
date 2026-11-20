"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Panel } from "@/components/ui/Panel";
import { RadioList } from "@/components/ui/RadioList";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { interviewDefaults, interviewQuestions, MODE_OPTIONS } from "../data";
import { interviewQuery, modeLabel, parseMode, readJob } from "../lib";
import type { InterviewMode } from "../types";

type Errors = { job?: string; coverLetter?: string; consent?: string };

/** 모의면접 1단계: 설정. 입력을 검사한 뒤 장비 점검으로 넘어간다. */
export function SetupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [job, setJob] = useState(() => readJob(params.get("job")));
  const [coverLetter, setCoverLetter] = useState<string>(interviewDefaults.coverLetter);
  const [mode, setMode] = useState<InterviewMode>(() => parseMode(params.get("mode")));
  const [consent, setConsent] = useState(true);
  const [errors, setErrors] = useState<Errors>({});

  function validate(nextMode: InterviewMode): Errors {
    const next: Errors = {};
    if (!job.trim()) next.job = "희망 직무를 입력해 주세요.";
    if (!coverLetter.trim()) next.coverLetter = "자기소개서를 입력해 주세요.";
    if (nextMode === "camera" && !consent) next.consent = "음성 + 카메라로 진행하려면 카메라 분석에 동의해 주세요.";
    return next;
  }

  function goToCheck(nextMode: InterviewMode) {
    const next = validate(nextMode);
    setErrors(next);
    if (Object.keys(next).length > 0) return;
    router.push(`/interview/check?${interviewQuery({ job: job.trim(), mode: nextMode })}`);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    goToCheck(mode);
  }

  /** "카메라 없이 계속": 진행 방식을 음성만으로 바꿔 이동한다. 텍스트를 골랐으면 그대로 둔다. */
  function continueWithoutCamera() {
    const nextMode = mode === "text" ? "text" : "voice";
    setMode(nextMode);
    goToCheck(nextMode);
  }

  const summary = [
    { label: "직무", value: job.trim() || "입력 전" },
    { label: "유형", value: interviewDefaults.interviewType },
    { label: "질문", value: `${interviewQuestions.length}개` },
    { label: "진행 방식", value: modeLabel(mode) },
  ];

  return (
    <TwoColumn
      main={
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
          <TextField
            id="interview-job"
            label="희망 직무"
            value={job}
            onChange={(event) => setJob(event.target.value)}
            error={errors.job}
          />
          <TextArea
            id="interview-cover-letter"
            label="자기소개서"
            value={coverLetter}
            onChange={(event) => setCoverLetter(event.target.value)}
            error={errors.coverLetter}
          />
          <RadioList name="interview-mode" legend="진행 방식" options={MODE_OPTIONS} value={mode} onChange={setMode} />
          <div className="flex flex-col gap-2">
            <Checkbox checked={consent} onChange={setConsent}>
              <span className="text-body font-medium text-grey-900">카메라 분석에 동의해요</span>
              <span className="mt-0.5 text-small text-grey-600">
                시선과 고개 방향만 확인해요. 얼굴 이미지는 저장하지 않아요.
              </span>
            </Checkbox>
            {errors.consent && (
              <p role="alert" className="text-small text-red-500">
                {errors.consent}
              </p>
            )}
          </div>
          <div className="flex items-center gap-5">
            <Button type="submit">장비 점검하기</Button>
            <Button variant="text" onClick={continueWithoutCamera}>
              카메라 없이 계속
            </Button>
          </div>
        </form>
      }
      rail={
        <Panel as="aside" aria-labelledby="interview-summary" className="flex flex-col gap-3.5 p-5">
          <h2 id="interview-summary" className="text-h3 font-bold text-grey-900">
            이번 면접
          </h2>
          <dl className="flex flex-col gap-3.5 text-small" aria-live="polite">
            {summary.map((row) => (
              <div key={row.label} className="flex justify-between gap-3">
                <dt className="text-grey-600">{row.label}</dt>
                <dd className="text-right font-bold text-grey-900">{row.value}</dd>
              </div>
            ))}
          </dl>
          <hr className="border-grey-200" />
          <p className="text-small text-grey-600">시연에서는 준비된 질문과 예시 답변을 사용해요.</p>
        </Panel>
      }
    />
  );
}
