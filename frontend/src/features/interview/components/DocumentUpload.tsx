"use client";

import { FileText, Paperclip, X } from "lucide-react";
import { type ChangeEvent, type DragEvent, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { ATTACHMENT_ACCEPT, attachmentError } from "@/features/mentor/data";

export type UploadedDocument = {
  name: string;
  sizeBytes: number;
  /** uploading: 올리는 중 · extracting: 글자 읽는 중 · ready: 면접에 쓸 수 있음 · failed: 실패 */
  status: "uploading" | "extracting" | "ready" | "failed";
  documentId?: string;
  charCount?: number;
  error?: string;
};

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))}KB` : `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

const STATUS_TEXT: Record<UploadedDocument["status"], string> = {
  uploading: "올리는 중",
  extracting: "글자 읽는 중",
  ready: "준비됨",
  failed: "실패",
};

/**
 * 모의면접 서류 PDF 올리기. 눌러서 고르거나 끌어다 놓는다 (PDF 1개, 10MB 이하, AI 멘토 첨부와 같은 조건).
 * 파일을 고르면 `onPick`을 부르고, 올리기·글자 추출 상태는 위에서 `document`로 받아 보여준다.
 */
export function DocumentUpload({
  file,
  onPick,
  onRemove,
  error,
}: {
  file: UploadedDocument | null;
  onPick: (file: File) => void;
  onRemove: () => void;
  /** 면접 시작 때 검사한 오류 (예: PDF를 올려 주세요) */
  error?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const pickButtonRef = useRef<HTMLButtonElement>(null);
  const [pickError, setPickError] = useState<string | null>(null);
  const errorId = useId();
  // 자식 요소 위를 지날 때도 dragenter/dragleave가 나서, 들어온 횟수로 끌어 놓는 중인지 판단한다
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  function pick(files: FileList | null | undefined) {
    const picked = files?.[0];
    if (!picked) return;
    if (files.length > 1) {
      setPickError("파일은 한 번에 하나만 올릴 수 있어요.");
      return;
    }
    const problem = attachmentError(picked);
    setPickError(problem);
    if (!problem) onPick(picked);
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    pick(event.target.files);
    event.target.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
  }

  const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");

  function handleDragEnter(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function handleDragOver(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault(); // 브라우저가 PDF를 새로 여는 것을 막아야 drop이 온다
    event.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    pick(event.dataTransfer.files);
  }

  const shownError = file?.error ?? pickError ?? error;

  return (
    <div className="flex w-full flex-col gap-1.5">
      <input
        ref={inputRef}
        type="file"
        accept={ATTACHMENT_ACCEPT}
        onChange={handleFile}
        tabIndex={-1}
        aria-hidden
        className="hidden"
      />
      {file ? (
        <div
          className={cn(
            "flex items-center gap-3 rounded-field border bg-white py-3 pr-2.5 pl-3.75",
            file.status === "failed" ? "border-red-500" : "border-grey-300",
          )}
        >
          <FileText aria-hidden className="size-5 shrink-0 text-grey-600" strokeWidth={2} />
          <div className="flex min-w-0 flex-1 flex-col">
            <p className="truncate text-body font-medium text-grey-900">
              <span className="sr-only">올린 파일: </span>
              {file.name}
            </p>
            <p className="text-small text-grey-600" aria-live="polite">
              {formatSize(file.sizeBytes)} ·{" "}
              <span className={cn(file.status === "ready" && "text-blue-500", file.status === "failed" && "text-red-500")}>
                {STATUS_TEXT[file.status]}
              </span>
              {file.status === "ready" && file.charCount !== undefined && ` · ${file.charCount.toLocaleString()}자`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              onRemove();
              setPickError(null);
              pickButtonRef.current?.focus();
            }}
            aria-label={`${file.name} 빼기`}
            className="flex size-8 shrink-0 items-center justify-center rounded-control text-grey-500 hover:bg-grey-100 hover:text-grey-800"
          >
            <X aria-hidden className="size-4" strokeWidth={2} />
          </button>
        </div>
      ) : (
        <div
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "flex w-full flex-col items-center gap-2 rounded-field border border-dashed px-4 py-7 text-center",
            dragging ? "border-blue-500 bg-blue-50" : shownError ? "border-red-500" : "border-grey-300",
          )}
        >
          <button
            ref={pickButtonRef}
            type="button"
            onClick={() => inputRef.current?.click()}
            aria-describedby={shownError ? errorId : undefined}
            className="inline-flex h-9.5 items-center gap-1.5 rounded-control border border-grey-300 bg-white px-3.5 text-btn-s font-medium text-grey-800 hover:bg-grey-50"
          >
            <Paperclip aria-hidden className="size-4" strokeWidth={2} />
            PDF 고르기
          </button>
          <p className="text-small text-grey-600">
            {dragging ? "여기에 놓으면 올라가요" : "또는 여기에 끌어다 놓기 · PDF 1개, 10MB 이하"}
          </p>
        </div>
      )}
      {shownError && (
        <p id={errorId} role="alert" className="text-small text-red-500">
          {shownError}
        </p>
      )}
    </div>
  );
}
