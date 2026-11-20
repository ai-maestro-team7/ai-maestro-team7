"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Chip } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import { RadioList } from "@/components/ui/RadioList";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { loginHref } from "@/features/auth/lib";
import { ApiError, AUTH_REQUIRED } from "@/lib/api";
import { startInterview } from "../api";
import { interviewDefaults, MODE_OPTIONS, RULES, TYPE_OPTIONS } from "../data";
import { interviewQuery, modeLabel, parseMode, readJob, typeLabel } from "../lib";
import type { InterviewMode, InterviewType } from "../types";

type Errors = { job?: string; coverLetter?: string; consent?: string };

/** 모의면접 1단계: 설정. 입력을 검사하고 세션을 만든 뒤(`POST /interview/start`) 장비 점검으로 넘어간다. */
export function SetupForm() {
  const router = useRouter();
  const params = useSearchParams();
  const [job, setJob] = useState(() => readJob(params.get("job")));
  const [coverLetter, setCoverLetter] = useState<string>(interviewDefaults.coverLetter);
  const [interviewType, setInterviewType] = useState<InterviewType>(interviewDefaults.interviewType);
  const [mode, setMode] = useState<InterviewMode>(() => parseMode(params.get("mode")));
  const [consent, setConsent] = useState(true);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<{ message: string; needsLogin: boolean }>();
  const [pending, setPending] = useState(false);

  function validate(nextMode: InterviewMode): Errors {
    const next: Errors = {};
    const trimmedJob = job.trim();
    if (!trimmedJob) next.job = "희망 직무를 입력해 주세요.";
    else if (trimmedJob.length > RULES.jobMax) next.job = `희망 직무는 ${RULES.jobMax}자까지 쓸 수 있어요.`;
    if (coverLetter.length < RULES.resumeMin) next.coverLetter = `자기소개서를 ${RULES.resumeMin}자 이상 입력해 주세요.`;
    else if (coverLetter.length > RULES.resumeMax)
      next.coverLetter = `자기소개서는 ${RULES.resumeMax.toLocaleString()}자까지 쓸 수 있어요.`;
    if (nextMode === "camera" && !consent) next.consent = "음성 + 카메라로 진행하려면 카메라 분석에 동의해 주세요.";
    return next;
  }

  async function start(nextMode: InterviewMode) {
    const next = validate(nextMode);
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setPending(true);
    setFailure(undefined);
    try {
      const { sessionId } = await startInterview({
        job: job.trim(),
        resumeText: coverLetter,
        interviewType,
        // 카메라 방식이고 동의했을 때만 시선을 본다. 그 밖에는 태도가 측정되지 않는다
        cameraConsent: nextMode === "camera" && consent,
      });
      router.push(`/interview/check?${interviewQuery({ session: sessionId, job: job.trim(), mode: nextMode })}`);
    } catch (e) {
      const needsLogin = e instanceof ApiError && e.code === AUTH_REQUIRED;
      setFailure({
        needsLogin,
        message: needsLogin
          ? "로그인하면 모의면접을 시작할 수 있어요."
          : e instanceof ApiError && e.status === 400
            ? e.message
            : "면접을 준비하지 못했어요. 잠시 뒤 다시 시도해 주세요.",
      });
      setPending(false);
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void start(mode);
  }

  /** "카메라 없이 계속": 진행 방식을 음성만으로 바꿔 시작한다. 텍스트를 골랐으면 그대로 둔다. */
  function continueWithoutCamera() {
    const nextMode = mode === "text" ? "text" : "voice";
    setMode(nextMode);
    void start(nextMode);
  }

  const summary = [
    { label: "직무", value: job.trim() || "입력 전" },
    { label: "유형", value: typeLabel(interviewType) },
    { label: "질문", value: `${RULES.baseQuestions}개 + 꼬리질문` },
    { label: "진행 방식", value: modeLabel(mode) },
  ];

  return (
    <TwoColumn
      main={
        <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
          <TextField
            id="interview-job"
            label="희망 직무"
            maxLength={RULES.jobMax}
            value={job}
            onChange={(event) => setJob(event.target.value)}
            error={errors.job}
          />
          <TextArea
            id="interview-cover-letter"
            label="자기소개서"
            rows={5}
            value={coverLetter}
            onChange={(event) => setCoverLetter(event.target.value)}
            error={errors.coverLetter}
            counterSuffix={`/ ${RULES.resumeMin}~${RULES.resumeMax.toLocaleString()}자`}
          />
          <fieldset className="flex w-full flex-col">
            <legend className="mb-2 text-small font-medium text-grey-700">면접 유형</legend>
            <div className="flex flex-wrap gap-2">
              {TYPE_OPTIONS.map((option) => (
                <Chip key={option.value} selected={interviewType === option.value} onClick={() => setInterviewType(option.value)}>
                  {option.label}
                </Chip>
              ))}
            </div>
          </fieldset>
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
          {failure && (
            <p role="alert" className="flex flex-wrap items-center gap-3 text-small text-red-500">
              {failure.message}
              {failure.needsLogin && (
                <Button href={loginHref("/interview/")} size="M">
                  로그인
                </Button>
              )}
            </p>
          )}
          <div className="flex items-center gap-5">
            <Button type="submit" disabled={pending}>
              {pending ? "면접 준비 중" : "장비 점검하기"}
            </Button>
            <Button variant="text" onClick={continueWithoutCamera} disabled={pending}>
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
          <p className="text-small text-grey-600">
            질문은 자기소개서와 희망 직무로 만들어요. 답변은 질문마다 {RULES.answerLimitSec / 60}분까지 할 수 있어요.
          </p>
        </Panel>
      }
    />
  );
}
