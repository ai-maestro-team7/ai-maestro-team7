"use client";

import { FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { SubTabs } from "@/components/ui/SubTabs";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import { diagnosisDefaults } from "../data";
import type { DiagnosisInputTab } from "../types";

type Errors = { file?: string; text?: string; role?: string };

const TABS: { key: DiagnosisInputTab; label: string }[] = [
  { key: "PDF", label: "PDF 업로드" },
  { key: "TEXT", label: "직접 입력" },
];

/**
 * 이력서·직무 진단 입력. 고른 PDF는 파일 이름만 보여주고 어디에도 보내지 않는다 (업로드 API 연결 전).
 */
export function DiagnosisForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<DiagnosisInputTab>("PDF");
  const [fileName, setFileName] = useState<string>(diagnosisDefaults.fileName);
  const [fileNote, setFileNote] = useState<string>(diagnosisDefaults.fileNote);
  const [text, setText] = useState("");
  const [role, setRole] = useState<string>(diagnosisDefaults.targetRole);
  const [errors, setErrors] = useState<Errors>({});

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrors((prev) => ({ ...prev, file: "PDF 파일만 고를 수 있어요." }));
      return;
    }
    setFileName(file.name);
    setFileNote("이 기기에서 고른 파일이에요 · 시연에서는 내용을 읽지 않아요");
    setErrors((prev) => ({ ...prev, file: undefined }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: Errors = {};
    if (!role.trim()) next.role = "목표 직무를 입력해 주세요.";
    if (tab === "PDF" && !fileName) next.file = "이력서 PDF를 골라 주세요.";
    if (tab === "TEXT" && !text.trim()) next.text = "이력서 내용을 입력해 주세요.";
    setErrors(next);
    if (Object.keys(next).length === 0) router.push("/diagnosis/result");
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="flex w-full flex-col gap-6">
      <div className="flex flex-col gap-3">
        <SubTabs label="이력서 입력 방식" items={TABS} activeKey={tab} onChange={setTab} panelId="resume-input" />
        <div id="resume-input" role="tabpanel">
          {tab === "PDF" ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-3 rounded-field border border-grey-300 px-4.25 py-3.75">
                <FileText aria-hidden className="size-5 shrink-0 text-grey-600" strokeWidth={2} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <p className="truncate text-body text-grey-900">{fileName}</p>
                  <p className="text-small text-grey-600">{fileNote}</p>
                </div>
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="shrink-0 text-small font-medium text-blue-500"
                >
                  바꾸기<span className="sr-only"> (이력서 PDF 고르기)</span>
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf,.pdf"
                  onChange={handleFile}
                  className="sr-only"
                  tabIndex={-1}
                  aria-hidden
                />
              </div>
              {errors.file && (
                <p role="alert" className="text-small text-red-500">
                  {errors.file}
                </p>
              )}
            </div>
          ) : (
            <TextArea
              id="resume-text"
              label="이력서 내용"
              value={text}
              onChange={(event) => setText(event.target.value)}
              rows={6}
              placeholder="경력, 기술, 프로젝트를 적어 주세요. 실명·연락처는 적지 않아요."
              error={errors.text}
            />
          )}
        </div>
      </div>

      <TextField
        id="target-role"
        label="목표 직무"
        value={role}
        onChange={(event) => setRole(event.target.value)}
        error={errors.role}
      />

      <div>
        <Button type="submit">이 이력서로 진단하기</Button>
      </div>
    </form>
  );
}
