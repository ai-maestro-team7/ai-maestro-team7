"use client";

import { Briefcase, FileUp } from "lucide-react";
import { type ChangeEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { ApiError } from "@/lib/api";
import { ATTACHMENT_ACCEPT } from "@/features/mentor/data";
import { readJobPostingText } from "../api";
import { RULES } from "../data";

/** 채팅이나 공고 상세에서 함께 넘어온 공고 */
export type LinkedJobPosting = { jobPostingId: string; title?: string; organization?: string };

export type JobPostingDraft = { title: string; company: string; text: string };

const PDF_MAX_BYTES = 4 * 1024 * 1024; // 서버 `/job-posting/text` 한도와 같다

function readFailure(error: unknown): string {
  if (error instanceof ApiError && [400, 413, 422].includes(error.status)) return error.message;
  return "PDF를 읽지 못했어요. 잠시 뒤 다시 시도하거나 공고 내용을 붙여 넣어 주세요.";
}

/**
 * 면접 설정의 채용 공고 (선택, #167). 질문을 공고의 업무·요건에 맞춰 만든다 (C #158).
 * - 공고와 함께 들어왔으면(`linked`) 그 공고를 보여 주고 올리기를 끈다
 * - 바로 들어왔으면 붙여넣기와 PDF 불러오기를 켠다. PDF는 서버가 글자만 읽어 돌려주고, 입력칸에서 고칠 수 있다
 */
export function JobPostingField({
  linked,
  draft,
  onChange,
  error,
  disabled,
}: {
  linked: LinkedJobPosting | null;
  draft: JobPostingDraft;
  onChange: (draft: JobPostingDraft) => void;
  error?: string;
  disabled?: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState<string>();
  const [notice, setNotice] = useState<string>();

  async function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
    if (!file) return;
    setNotice(undefined);
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setReadError("PDF 파일만 올릴 수 있어요.");
      return;
    }
    if (file.size > PDF_MAX_BYTES) {
      setReadError("4MB 이하 PDF만 올릴 수 있어요.");
      return;
    }
    setReading(true);
    setReadError(undefined);
    try {
      const read = await readJobPostingText(file);
      onChange({ ...draft, text: read.text });
      setNotice(
        read.truncated
          ? `PDF 글이 ${read.charCount.toLocaleString()}자라서 앞의 ${RULES.postingMax.toLocaleString()}자만 가져왔어요. 면접에 쓸 부분인지 확인해 주세요.`
          : `${file.name}에서 ${read.text.length.toLocaleString()}자를 가져왔어요. 고칠 부분이 있으면 고쳐 주세요.`,
      );
    } catch (e) {
      setReadError(readFailure(e));
    } finally {
      setReading(false);
    }
  }

  if (linked) {
    return (
      <fieldset className="flex w-full flex-col">
        <legend className="mb-2 text-small font-medium text-grey-700">채용 공고</legend>
        <div className="flex items-start gap-3 rounded-field border border-grey-200 bg-grey-50 px-4 py-3.5">
          <Briefcase aria-hidden className="mt-0.5 size-5 shrink-0 text-grey-600" strokeWidth={2} />
          <div className="flex min-w-0 flex-col gap-0.5">
            <p className="text-body font-bold text-grey-900">{linked.title ?? "선택한 공고"}</p>
            {linked.organization && <p className="text-small text-grey-700">{linked.organization}</p>}
            <p className="mt-1 text-small text-grey-600">
              이 공고의 업무·요건에 맞춰 질문을 만들어요. 공고와 함께 들어와서 다른 공고는 올릴 수 없어요.
            </p>
          </div>
        </div>
      </fieldset>
    );
  }

  return (
    <fieldset className="flex w-full flex-col gap-3" disabled={disabled}>
      <legend className="mb-2 text-small font-medium text-grey-700">채용 공고 (선택)</legend>
      <p className="-mt-1 text-small text-grey-600">
        공고를 넣으면 그 공고에 맞춰 면접 질문을 만들어요. 공고 내용은 질문을 만드는 데만 써요.
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField
          id="interview-posting-title"
          label="공고 제목 (선택)"
          maxLength={RULES.postingTitleMax}
          placeholder="예: 데이터 분석 신입"
          value={draft.title}
          onChange={(event) => onChange({ ...draft, title: event.target.value })}
        />
        <TextField
          id="interview-posting-company"
          label="회사 (선택)"
          maxLength={RULES.postingCompanyMax}
          placeholder="예: (주)가상데이터"
          value={draft.company}
          onChange={(event) => onChange({ ...draft, company: event.target.value })}
        />
      </div>
      <TextArea
        id="interview-posting-text"
        label="공고 내용"
        rows={5}
        value={draft.text}
        onChange={(event) => onChange({ ...draft, text: event.target.value })}
        placeholder="담당 업무, 자격 요건, 우대 사항을 붙여 넣거나 PDF에서 불러오세요"
        error={error}
        counterSuffix={`/ ${RULES.postingMax.toLocaleString()}자 · 비워 두면 공고 없이 진행`}
      />
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={inputRef}
          type="file"
          accept={ATTACHMENT_ACCEPT}
          onChange={(event) => void handleFile(event)}
          tabIndex={-1}
          aria-hidden
          className="hidden"
        />
        <Button variant="line" size="M" onClick={() => inputRef.current?.click()} disabled={reading || disabled}>
          <FileUp aria-hidden className="mr-1.5 size-4" strokeWidth={2} />
          {reading ? "PDF 읽는 중" : "PDF에서 불러오기"}
        </Button>
        <span className="text-small text-grey-600">PDF 1개, 4MB 이하 · 파일은 저장하지 않아요</span>
      </div>
      {notice && (
        <p role="status" className="text-small text-grey-700">
          {notice}
        </p>
      )}
      {readError && (
        <p role="alert" className="text-small text-red-500">
          {readError}
        </p>
      )}
    </fieldset>
  );
}
