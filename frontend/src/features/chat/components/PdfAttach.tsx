"use client";

import { FileText, Paperclip } from "lucide-react";
import { type ChangeEvent, type DragEvent, type ReactNode, useRef, useState } from "react";

const INPUT_ID = "chat-pdf-input";

type DocKind = "RESUME" | "COVER_LETTER";
import { createPdfDocument, errorMessage, getDocument, poll } from "@/features/mentoring/api";
import { ATTACHMENT_ACCEPT, attachmentError } from "@/features/mentor/data";
import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";

/**
 * 이력서·자기소개서 PDF 첨부 (#127의 첨부 화면을 채팅에 옮김). 고르거나 끌어다 놓으면 A 문서 API로 올리고
 * 글자·역량 추출이 끝나면 문서 ID를 넘긴다. 파일 내용은 채팅 메시지로 보내지 않는다 (개발계획서4 §2.2).
 */
export function PdfDropZone({
  disabled,
  onReady,
  onProcessingChange,
  children,
}: {
  disabled: boolean;
  /** 고르기·올리기·글자 찾기 중이면 true. 채팅이 그동안 보내기를 막는다 */
  onProcessingChange: (processing: boolean) => void;
  onReady: (documentId: string, fileName: string, kind: DocKind) => void;
  children: ReactNode;
}) {
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 고른 파일. 이력서인지 자기소개서인지 고른 뒤 올린다 (자소서로 올려야 면접 체험에서 바로 쓸 수 있다)
  const [picked, setPicked] = useState<File | null>(null);

  function pick(files: FileList | null | undefined) {
    const file = files?.[0];
    if (!file || disabled || uploading) return;
    if (files.length > 1) {
      setError("파일은 한 번에 하나만 붙일 수 있어요.");
      return;
    }
    const problem = attachmentError(file);
    setError(problem);
    setPicked(problem ? null : file);
    onProcessingChange(!problem);
  }

  async function upload(file: File, kind: DocKind) {
    setPicked(null);
    setUploading(file.name);
    try {
      const created = await createPdfDocument(file, kind);
      await poll(() => getDocument(created.documentId));
      onProcessingChange(false); // 끝난 뒤에 보내야 send가 막히지 않는다
      onReady(created.documentId, file.name, kind);
    } catch (e) {
      setError(errorMessage(e));
      onProcessingChange(false);
    } finally {
      setUploading(null);
    }
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    pick(event.target.files);
    event.target.value = ""; // 같은 파일을 다시 고를 수 있게 비운다
  }

  const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");
  function onDragEnter(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }
  function onDragOver(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault(); // 브라우저가 PDF를 새로 여는 것을 막아야 drop이 온다
    event.dataTransfer.dropEffect = "copy";
  }
  function onDragLeave(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }
  function onDrop(event: DragEvent<HTMLDivElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    pick(event.dataTransfer.files);
  }

  return (
    <div
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      className="relative flex w-full flex-col gap-1.5"
    >
      {dragging && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-field border border-blue-500 bg-blue-50 text-small font-medium text-blue-500"
        >
          <FileText className="size-5" strokeWidth={2} />
          여기에 놓으면 이력서·자기소개서 PDF가 첨부돼요
        </div>
      )}
      <input id={INPUT_ID} type="file" accept={ATTACHMENT_ACCEPT} onChange={handleFile} className="sr-only" tabIndex={-1} />
      {children}
      {picked && (
        <div className="flex flex-wrap items-center gap-2 text-small text-grey-800">
          <span>‘{picked.name}’은</span>
          <Chip onClick={() => void upload(picked, "RESUME")}>이력서예요</Chip>
          <Chip onClick={() => void upload(picked, "COVER_LETTER")}>자기소개서예요</Chip>
          <Chip
            onClick={() => {
              setPicked(null);
              onProcessingChange(false);
            }}
          >
            취소
          </Chip>
        </div>
      )}
      {uploading && (
        <p role="status" className="text-small text-grey-600">
          ‘{uploading}’에서 글자와 역량을 찾고 있어요. 1분쯤 걸려요.
        </p>
      )}
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}

/** 입력칸 왼쪽 클립 버튼. 누르면 숨긴 파일 선택 칸을 연다 */
export function AttachButton({ disabled }: { disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={() => document.getElementById(INPUT_ID)?.click()}
      disabled={disabled}
      aria-label="이력서·자기소개서 PDF 첨부"
      className={cn(
        "inline-flex size-9.5 shrink-0 items-center justify-center rounded-control text-grey-600 hover:bg-grey-100",
        "disabled:cursor-not-allowed disabled:opacity-40",
      )}
    >
      <Paperclip aria-hidden className="size-5" strokeWidth={2} />
    </button>
  );
}
