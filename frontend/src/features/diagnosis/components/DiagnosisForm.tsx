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
import {
  createAnalysis,
  createPdfDocument,
  createTextDocument,
  errorMessage,
  getAnalysis,
  getDocument,
  getProfile,
  poll,
  saveFlow,
} from "@/features/mentoring/api";

type Errors = { file?: string; text?: string; role?: string };

const TABS: { key: DiagnosisInputTab; label: string }[] = [
  { key: "PDF", label: "PDF 업로드" },
  { key: "TEXT", label: "직접 입력" },
];

const DATA_ANALYSIS_NCS = "20010105";

/** 이력서 문서 → 역량 프로필 → NCS 직무 적합도 분석을 한 흐름으로 시작한다. */
export function DiagnosisForm() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [tab, setTab] = useState<DiagnosisInputTab>("PDF");
  const [file, setFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState<string>(diagnosisDefaults.fileName);
  const [fileNote, setFileNote] = useState<string>(diagnosisDefaults.fileNote);
  const [text, setText] = useState("");
  const [role, setRole] = useState<string>(diagnosisDefaults.targetRole);
  const [errors, setErrors] = useState<Errors>({});
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState("");
  const [submitError, setSubmitError] = useState("");

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
      setErrors((prev) => ({ ...prev, file: "PDF 파일만 고를 수 있어요." }));
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      setErrors((prev) => ({ ...prev, file: "10MB 이하 PDF만 올릴 수 있어요." }));
      return;
    }
    setFile(file);
    setFileName(file.name);
    setFileNote(`${(file.size / 1024 / 1024).toFixed(1)}MB · 실제 분석에 사용돼요`);
    setErrors((prev) => ({ ...prev, file: undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next: Errors = {};
    if (!role.trim()) next.role = "목표 직무를 입력해 주세요.";
    if (role.trim() !== "데이터 분석" && role.trim() !== "빅데이터 분석") {
      next.role = "현재 실제 데이터가 연결된 데모 직무는 데이터 분석이에요.";
    }
    if (tab === "PDF" && !file) next.file = "이력서 PDF를 골라 주세요.";
    if (tab === "TEXT" && text.trim().length < 1000) next.text = "이력서 내용을 1,000자 이상 입력해 주세요.";
    setErrors(next);
    if (Object.keys(next).length > 0) return;

    setSubmitting(true);
    setSubmitError("");
    try {
      setProgress(tab === "PDF" ? "PDF를 안전하게 업로드하고 있어요" : "이력서 내용을 등록하고 있어요");
      const document = tab === "PDF" ? await createPdfDocument(file!) : await createTextDocument(text.trim());

      setProgress("이력서에서 역량과 근거를 찾고 있어요");
      await poll(() => getDocument(document.documentId));

      setProgress("역량 프로필을 직무 요건과 비교하고 있어요");
      const profile = await getProfile();
      const created = await createAnalysis(profile, DATA_ANALYSIS_NCS);
      if (!created.analysisId) throw new Error("분석 ID를 받지 못했어요.");
      saveFlow({
        targetRole: "데이터 분석",
        targetNcsCode: DATA_ANALYSIS_NCS,
        documentId: document.documentId,
        profileId: profile.profileId,
        profileVersion: profile.profileVersion,
        analysisId: created.analysisId,
      });
      await poll(() => getAnalysis(created.analysisId!));
      router.push("/diagnosis/result");
    } catch (error) {
      setSubmitError(errorMessage(error));
      setProgress("");
    } finally {
      setSubmitting(false);
    }
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
                  <p className="truncate text-body text-grey-900">{fileName || "선택한 PDF가 없어요"}</p>
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
        disabled={submitting}
      />

      <p className="text-small text-grey-600">현재 실제 기준 데이터는 NCS 빅데이터분석(20010105)에 연결돼 있어요.</p>

      {progress && (
        <p role="status" aria-live="polite" className="rounded-field bg-blue-50 px-4 py-3 text-body text-blue-500">
          {progress}
        </p>
      )}
      {submitError && (
        <div role="alert" className="rounded-field bg-grey-50 px-4 py-3">
          <p className="text-body font-bold text-grey-900">진단을 시작하지 못했어요</p>
          <p className="mt-1 text-small text-grey-700">{submitError}</p>
        </div>
      )}

      <div>
        <Button type="submit" disabled={submitting}>
          {submitting ? "분석 중이에요" : "이 이력서로 진단하기"}
        </Button>
      </div>
    </form>
  );
}
