"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Chip } from "@/components/ui/Chip";
import { Panel } from "@/components/ui/Panel";
import { RadioList } from "@/components/ui/RadioList";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { loginHref } from "@/features/auth/lib";
import { useSessionOwner } from "@/features/auth/useSessionOwner";
import { fetchPosting } from "@/features/jobs/data";
import { parseHandoff, readHandoffRaw, subscribeHandoff } from "@/features/chat/lib";
import { createPdfDocument, errorMessage, waitForDocumentText } from "@/features/mentoring/api";
import { ApiError, AUTH_REQUIRED } from "@/lib/api";
import { sessionOwner } from "@/lib/session";
import { startInterview } from "../api";
import { interviewDefaults, MODE_OPTIONS, RULES, TYPE_OPTIONS } from "../data";
import { interviewQuery, modeLabel, parseMode, readJob, typeLabel } from "../lib";
import type { InterviewMode, InterviewType } from "../types";
import { DocumentUpload, type UploadedDocument } from "./DocumentUpload";
import { type JobPostingDraft, JobPostingField, type LinkedJobPosting } from "./JobPostingField";

type Errors = { job?: string; coverLetter?: string; document?: string; posting?: string };

/** 주소의 공고 ID (B 공고). `#`이나 이상한 값이면 없는 것으로 본다 */
function parsePostingId(value: string | null): string | null {
  return value && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}$/.test(value) ? value : null;
}

/** 서류를 넣는 방법: 직접 입력 또는 PDF 올리기 */
type DocumentSource = "text" | "pdf";
type DocumentKind = "COVER_LETTER" | "RESUME";

const SOURCE_OPTIONS: { value: DocumentSource; label: string }[] = [
  { value: "text", label: "직접 입력" },
  { value: "pdf", label: "PDF 올리기" },
];
const KIND_OPTIONS: { value: DocumentKind; label: string }[] = [
  { value: "COVER_LETTER", label: "자기소개서" },
  { value: "RESUME", label: "이력서" },
];

/**
 * 모의면접 1단계: 설정. 입력을 검사하고 세션을 만든 뒤(`POST /interview/start`) 장비 점검으로 넘어간다.
 * 진행 버튼은 오른쪽 "이번 면접" 요약 아래에 둬서, 바뀐 설정을 확인하고 진행하게 한다.
 * [장비 점검하기]는 카메라 분석에 동의해야 켜진다. 동의하지 않으면 [카메라 없이 계속]으로 진행한다.
 */
export function SetupForm() {
  const owner = useSessionOwner();
  // 계정이 바뀌면 인계 문서와 사용자가 고친 자소서를 포함한 폼 상태를 새로 만든다.
  return <InterviewSetup key={owner ?? "anonymous"} owner={owner} />;
}

function InterviewSetup({ owner }: { owner: string | null }) {
  const router = useRouter();
  const params = useSearchParams();
  const formId = useId();
  const hintId = useId();
  const [job, setJob] = useState(() => readJob(params.get("job")));
  // 채팅에서 넘어왔으면 넘겨받은 자소서를 채운다 (개발계획서4 §10). 서버 렌더에는 값이 없다
  const handoffRaw = useSyncExternalStore(subscribeHandoff, readHandoffRaw, () => null);
  const handoff = parseHandoff(handoffRaw);
  // 채팅에서 고른 저장된 자소서(A 문서)는 이미 올린 PDF처럼 보여 준다. 크기·글자 수는 모르니 길이는 서버가 확인한다
  const handoffDocument: UploadedDocument | null = handoff?.documentId
    ? { name: handoff.documentTitle ?? "저장된 자기소개서", status: "ready", documentId: handoff.documentId, saved: true }
    : null;
  const [editedCoverLetter, setCoverLetter] = useState<string | null>(null);
  const coverLetter = editedCoverLetter ?? handoff?.coverLetter ?? interviewDefaults.coverLetter;
  const [chosenSource, setSource] = useState<DocumentSource | null>(null);
  const source: DocumentSource = chosenSource ?? (handoffDocument ? "pdf" : "text");
  const [kind, setKind] = useState<DocumentKind>("COVER_LETTER");
  // undefined: 아직 고르지 않음(채팅 인계 문서를 쓴다) · null: 뺐음
  const [pickedPdf, setPdf] = useState<UploadedDocument | null | undefined>(undefined);
  const pdf = pickedPdf === undefined ? handoffDocument : pickedPdf;
  // 채팅·공고 상세에서 공고와 함께 오면 주소에 ?posting=이 붙는다. 그때만 그 공고로 질문을 만들고 공고 올리기를 끈다.
  // 메뉴로 바로 들어오면 공고가 없으니 붙여넣기·PDF 올리기를 켠다 (#167)
  const postingId = parsePostingId(params.get("posting"));
  const handoffPosting = handoff?.posting?.jobPostingId === postingId ? handoff?.posting : undefined;
  const hasHandoffPosting = handoffPosting !== undefined;
  const [fetchedPosting, setFetchedPosting] = useState<LinkedJobPosting | null>(null);
  useEffect(() => {
    if (!postingId || hasHandoffPosting) return;
    let active = true;
    // 공고 상세에서 오면 제목·기관을 B 공고 상세에서 읽는다. 못 읽어도 공고 ID로 면접은 시작할 수 있다
    fetchPosting(postingId).then(
      ({ posting }) => active && setFetchedPosting({ jobPostingId: postingId, title: posting.title, organization: posting.organization }),
      () => undefined,
    );
    return () => {
      active = false;
    };
  }, [postingId, hasHandoffPosting]);
  const linkedPosting: LinkedJobPosting | null = postingId
    ? (handoffPosting ?? (fetchedPosting?.jobPostingId === postingId ? fetchedPosting : { jobPostingId: postingId }))
    : null;
  const [postingDraft, setPostingDraft] = useState<JobPostingDraft>({ title: "", company: "", text: "" });
  // 올리는 중에 파일을 빼거나 바꾸면 앞의 요청 결과를 버린다
  const upload = useRef<AbortController | null>(null);
  useEffect(() => () => upload.current?.abort(), []);
  const [interviewType, setInterviewType] = useState<InterviewType>(interviewDefaults.interviewType);
  const [mode, setMode] = useState<InterviewMode>(() => parseMode(params.get("mode")));
  const [consent, setConsent] = useState(true);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<{ message: string; needsLogin: boolean }>();
  const [pending, setPending] = useState(false);

  function validate(): Errors {
    const next: Errors = {};
    const trimmedJob = job.trim();
    if (!trimmedJob) next.job = "희망 직무를 입력해 주세요.";
    else if (trimmedJob.length > RULES.jobMax) next.job = `희망 직무는 ${RULES.jobMax}자까지 쓸 수 있어요.`;
    if (source === "text") {
      if (coverLetter.length < RULES.resumeMin) next.coverLetter = `자기소개서를 ${RULES.resumeMin}자 이상 입력해 주세요.`;
      else if (coverLetter.length > RULES.resumeMax)
        next.coverLetter = `자기소개서는 ${RULES.resumeMax.toLocaleString()}자까지 쓸 수 있어요.`;
    } else if (!pdf || pdf.status === "failed") next.document = "자기소개서나 이력서 PDF를 올려 주세요.";
    else if (pdf.status !== "ready") next.document = "PDF를 읽고 있어요. 끝나면 진행할 수 있어요.";
    else if (pdf.charCount !== undefined && pdf.charCount < RULES.resumeMin)
      next.document = `PDF에서 읽은 글이 ${RULES.resumeMin}자보다 적어요. 다른 파일을 올리거나 직접 입력해 주세요.`;
    else if (pdf.charCount !== undefined && pdf.charCount > RULES.resumeMax)
      next.document = `PDF 글이 ${RULES.resumeMax.toLocaleString()}자를 넘어요. 면접에 쓸 부분만 직접 입력해 주세요.`;
    const postingText = postingDraft.text.trim();
    if (!linkedPosting && postingText && postingText.length < RULES.postingMin)
      next.posting = `공고 내용을 ${RULES.postingMin}자 이상 넣거나 비워 두세요.`;
    else if (!linkedPosting && postingText.length > RULES.postingMax)
      next.posting = `공고 내용은 ${RULES.postingMax.toLocaleString()}자까지 넣을 수 있어요.`;
    return next;
  }

  /** PDF를 A 문서로 올리고(`/mentoring/documents`) 글자 추출이 끝날 때까지 기다린다. */
  async function handlePick(file: File) {
    upload.current?.abort();
    const controller = new AbortController();
    upload.current = controller;
    const base = { name: file.name, sizeBytes: file.size };
    setPdf({ ...base, status: "uploading" });
    setErrors((prev) => ({ ...prev, document: undefined }));
    try {
      const created = await createPdfDocument(file, kind);
      if (controller.signal.aborted) return;
      setPdf({ ...base, status: "extracting", documentId: created.documentId });
      const read = await waitForDocumentText(created.documentId, controller.signal);
      if (controller.signal.aborted) return;
      setPdf({ ...base, status: "ready", documentId: created.documentId, charCount: read.charCount });
    } catch (e) {
      if (controller.signal.aborted) return;
      setPdf({ ...base, status: "failed", error: errorMessage(e) });
    }
  }

  function removeDocument() {
    upload.current?.abort();
    upload.current = null;
    setPdf(null);
  }

  async function start(nextMode: InterviewMode) {
    // 다른 탭에서 로그인 계정이 바뀐 직후, 이전 렌더의 클릭 핸들러가 실행될 수 있다.
    if (owner !== sessionOwner()) return;
    const next = validate();
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setPending(true);
    setFailure(undefined);
    try {
      const { sessionId } = await startInterview({
        job: job.trim(),
        ...(source === "pdf" && pdf?.documentId ? { documentId: pdf.documentId } : { resumeText: coverLetter }),
        ...(linkedPosting
          ? { jobPostingId: linkedPosting.jobPostingId }
          : postingDraft.text.trim()
            ? {
                jobPosting: {
                  title: postingDraft.title.trim() || null,
                  company: postingDraft.company.trim() || null,
                  text: postingDraft.text.trim(),
                },
              }
            : {}),
        interviewType,
        // 카메라 방식이고 동의했을 때만 시선을 본다. 그 밖에는 태도가 측정되지 않는다
        cameraConsent: nextMode === "camera" && consent,
      });
      if (owner !== sessionOwner()) return;
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
    // 입력칸에서 Enter를 눌러도 동의 전에는 장비 점검으로 가지 않는다 (버튼이 꺼져 있다)
    if (!consent) return;
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
    {
      label: "서류",
      value:
        source === "text"
          ? `직접 입력 · ${coverLetter.length.toLocaleString()}자`
          : pdf?.status === "ready"
            ? pdf.saved
              ? "채팅에서 고른 서류"
              : `${KIND_OPTIONS.find((option) => option.value === kind)?.label} PDF`
            : "PDF 올리기 전",
    },
    {
      label: "채용 공고",
      value: linkedPosting
        ? (linkedPosting.title ?? "선택한 공고")
        : postingDraft.text.trim()
          ? `직접 입력 · ${postingDraft.text.trim().length.toLocaleString()}자`
          : "없음",
    },
    { label: "질문", value: `${RULES.baseQuestions}개 + 꼬리질문` },
    { label: "진행 방식", value: modeLabel(mode) },
  ];

  return (
    <TwoColumn
      main={
        <form id={formId} onSubmit={handleSubmit} noValidate className="flex flex-col gap-6">
          <TextField
            id="interview-job"
            label="희망 직무"
            maxLength={RULES.jobMax}
            value={job}
            onChange={(event) => setJob(event.target.value)}
            error={errors.job}
          />
          <fieldset className="flex w-full flex-col gap-3">
            <legend className="mb-2 text-small font-medium text-grey-700">자기소개서·이력서</legend>
            <div role="group" aria-label="서류 넣는 방법" className="flex flex-wrap gap-2">
              {SOURCE_OPTIONS.map((option) => (
                <Chip key={option.value} selected={source === option.value} onClick={() => setSource(option.value)}>
                  {option.label}
                </Chip>
              ))}
            </div>
            {source === "text" ? (
              <TextArea
                id="interview-cover-letter"
                label="자기소개서 내용"
                rows={5}
                value={coverLetter}
                onChange={(event) => setCoverLetter(event.target.value)}
                error={errors.coverLetter}
                counterSuffix={`/ ${RULES.resumeMin}~${RULES.resumeMax.toLocaleString()}자`}
              />
            ) : (
              <>
                {/* 종류는 올리기 전에 고른다. A 문서의 종류로 저장된다 */}
                <div role="group" aria-label="올릴 서류 종류" className="flex flex-wrap items-center gap-2">
                  <span className="mr-1 text-small text-grey-600">서류 종류</span>
                  {KIND_OPTIONS.map((option) => (
                    <Chip
                      key={option.value}
                      selected={kind === option.value}
                      onClick={() => setKind(option.value)}
                      disabled={pdf !== null && pdf.status !== "failed"}
                      className="disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {option.label}
                    </Chip>
                  ))}
                </div>
                <DocumentUpload file={pdf} onPick={handlePick} onRemove={removeDocument} error={errors.document} />
              </>
            )}
          </fieldset>
          <JobPostingField
            linked={linkedPosting}
            draft={postingDraft}
            onChange={(draft) => {
              setPostingDraft(draft);
              setErrors((prev) => (prev.posting ? { ...prev, posting: undefined } : prev));
            }}
            error={errors.posting}
            disabled={pending}
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
          <Checkbox checked={consent} onChange={setConsent}>
            <span className="text-body font-medium text-grey-900">카메라 분석에 동의해요</span>
            <span className="mt-0.5 text-small text-grey-600">
              시선과 고개 방향만 확인해요. 얼굴 이미지는 저장하지 않아요.
            </span>
          </Checkbox>
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
            질문은 자기소개서·이력서와 희망 직무{linkedPosting || postingDraft.text.trim() ? ", 채용 공고" : ""}로 만들어요. 답변은 질문마다 {RULES.answerLimitSec / 60}분까지 할 수 있어요.
          </p>
          {/* 버튼은 왼쪽 form 밖에 있어 form 속성으로 이어 준다 */}
          <div className="flex flex-col gap-1.5 pt-1.5">
            <Button
              type="submit"
              form={formId}
              fullWidth
              disabled={pending || !consent}
              aria-describedby={!consent ? hintId : undefined}
            >
              {pending ? "면접 준비 중" : "장비 점검하기"}
            </Button>
            <Button variant="text" fullWidth onClick={continueWithoutCamera} disabled={pending}>
              카메라 없이 계속
            </Button>
          </div>
          {!consent && (
            <p id={hintId} className="text-small text-grey-600">
              카메라 분석에 동의하면 장비 점검을 할 수 있어요. 카메라 없이 하려면 [카메라 없이 계속]을 눌러 주세요.
            </p>
          )}
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
        </Panel>
      }
    />
  );
}
