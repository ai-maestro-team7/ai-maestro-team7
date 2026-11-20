"use client";

import { FileText, Paperclip, X } from "lucide-react";
import { type ChangeEvent, type DragEvent, type FormEvent, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { cn } from "@/lib/cn";
import {
  ATTACHMENT_ACCEPT,
  ATTACHMENT_QUESTION,
  attachmentError,
  attachmentReply,
  FOLLOW_UP_EXAMPLE_LABEL,
  findMentorReply,
  MENTOR_DEFAULT_QUESTION,
  mentorExamples,
} from "../data";
import type { MentorAttachment, MentorExample, MentorTurn } from "../types";

function formatSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))}KB` : `${(bytes / 1024 / 1024).toFixed(1)}MB`;
}

/**
 * 홈 "AI 멘토에게 물어보기". 처음에는 입력 화면(Figma 홈), 질문을 보내면 대화 화면(Figma 홈 · AI 멘토 답변)으로 바뀐다.
 * 답변은 Mock 데이터에서 고르며 네트워크 요청을 보내지 않는다.
 * 이력서·자기소개서 PDF를 붙일 수 있다. 파일은 서버로 보내지 않고, 서류 종류에 맞는 진단·첨삭 화면을 안내한다.
 */
export function MentorPanel() {
  const [turns, setTurns] = useState<MentorTurn[]>([]);
  const [draft, setDraft] = useState(MENTOR_DEFAULT_QUESTION);
  const [attachment, setAttachment] = useState<MentorAttachment | null>(null);

  function ask(question: string, attached: MentorAttachment | null = null) {
    const trimmed = question.trim() || (attached ? ATTACHMENT_QUESTION : "");
    if (!trimmed) return;
    const reply = attached ? attachmentReply : findMentorReply(trimmed);
    setTurns((prev) => [...prev, { question: trimmed, attachment: attached ?? undefined, reply }]);
    setDraft("");
    setAttachment(null);
  }

  function reset() {
    setTurns([]);
    setDraft(MENTOR_DEFAULT_QUESTION);
    setAttachment(null);
  }

  const askBox = (placeholder: string) => (
    <AskBox
      value={draft}
      onChange={setDraft}
      attachment={attachment}
      onAttachmentChange={setAttachment}
      onSubmit={() => ask(draft, attachment)}
      placeholder={placeholder}
    />
  );

  const followUpExample = mentorExamples.find((example) => example.label === FOLLOW_UP_EXAMPLE_LABEL);
  const inConversation = turns.length > 0;

  return (
    <section aria-labelledby="mentor-title" className="flex min-w-0 flex-1 flex-col gap-3.5">
      <h2 id="mentor-title" className="text-h3 font-bold text-grey-900">
        AI 멘토에게 물어보기
      </h2>

      {inConversation ? (
        <div className="flex flex-col gap-4">
          <ol aria-live="polite" className="flex flex-col gap-4">
            {turns.map((turn, index) => (
              <li key={index} className="flex flex-col gap-4">
                <div className="flex max-w-[85%] flex-col items-end gap-2 self-end">
                  {turn.attachment && <AttachmentCard attachment={turn.attachment} />}
                  <p className="rounded-card bg-grey-100 px-3.5 py-2.5 text-body text-grey-900">
                    <span className="sr-only">내 질문: </span>
                    {turn.question}
                  </p>
                </div>
                <div className="flex flex-col gap-2.5">
                  <p className="text-small font-bold text-grey-600">AI 멘토</p>
                  <p className="text-body text-grey-900">{turn.reply.answer}</p>
                  {turn.reply.recommendations?.map((recommendation) => (
                    <div
                      key={recommendation.href}
                      className="flex items-center justify-between gap-3 rounded-field border border-grey-200 py-3 pr-3.5 pl-4"
                    >
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <p className="text-body font-bold text-grey-900">{recommendation.title}</p>
                        <p className="text-small text-grey-600">{recommendation.meta}</p>
                      </div>
                      <Button href={recommendation.href} variant="line" size="M">
                        {recommendation.actionLabel}
                      </Button>
                    </div>
                  ))}
                  <p className="text-small text-grey-600">시연용 답변이에요.</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            <Chip onClick={reset}>새 질문</Chip>
            {followUpExample && <ExampleChip example={followUpExample} onAsk={ask} />}
          </div>
          {askBox("이어서 물어보세요")}
        </div>
      ) : (
        <>
          {askBox("궁금한 점을 물어보세요")}
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-small text-grey-600">예시 질문</p>
            {mentorExamples.map((example) => (
              <ExampleChip key={example.label} example={example} onAsk={ask} />
            ))}
          </div>
          <p className="text-small text-grey-600">
            시연 모드에서는 준비된 답변을 보여드려요. 이력서·자기소개서 PDF를 클립 버튼으로 고르거나 입력칸에 끌어다
            놓을 수 있어요 (10MB 이하).
          </p>
        </>
      )}
    </section>
  );
}

function ExampleChip({ example, onAsk }: { example: MentorExample; onAsk: (question: string) => void }) {
  return <Chip onClick={() => onAsk(example.question)}>{example.label}</Chip>;
}

/** 보낸 질문 위에 보이는 첨부 파일 카드 */
function AttachmentCard({ attachment }: { attachment: MentorAttachment }) {
  return (
    <p className="flex max-w-full items-center gap-2.5 rounded-field border border-grey-200 bg-white py-2.5 pr-3.5 pl-3">
      <FileText aria-hidden className="size-5 shrink-0 text-grey-600" strokeWidth={2} />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-small font-medium text-grey-900">
          <span className="sr-only">첨부 파일: </span>
          {attachment.name}
        </span>
        <span className="text-small text-grey-600">
          PDF · {formatSize(attachment.sizeBytes)}
        </span>
      </span>
    </p>
  );
}

function AskBox({
  value,
  onChange,
  attachment,
  onAttachmentChange,
  onSubmit,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  attachment: MentorAttachment | null;
  onAttachmentChange: (attachment: MentorAttachment | null) => void;
  onSubmit: () => void;
  placeholder: string;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachButtonRef = useRef<HTMLButtonElement>(null);
  const [error, setError] = useState<string | null>(null);
  const errorId = useId();
  // 자식 요소 위를 지날 때도 dragenter/dragleave가 나서, 들어온 횟수로 끌어 놓는 중인지 판단한다
  const dragDepth = useRef(0);
  const [dragging, setDragging] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    onSubmit();
  }

  function attach(files: FileList | null | undefined) {
    const file = files?.[0];
    if (!file) return;
    if (files.length > 1) {
      setError("파일은 한 번에 하나만 붙일 수 있어요.");
      return;
    }
    const problem = attachmentError(file);
    setError(problem);
    if (problem) return;
    onAttachmentChange({ name: file.name, sizeBytes: file.size });
  }

  function handleFile(event: ChangeEvent<HTMLInputElement>) {
    attach(event.target.files);
    // 같은 파일을 다시 고를 수 있게 비운다
    event.target.value = "";
  }

  /** 글자나 링크가 아니라 파일을 끌고 있을 때만 반응한다 */
  const hasFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");

  function handleDragEnter(event: DragEvent<HTMLFormElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current += 1;
    setDragging(true);
  }

  function handleDragOver(event: DragEvent<HTMLFormElement>) {
    if (!hasFiles(event)) return;
    // 기본 동작(브라우저가 PDF를 새로 여는 것)을 막아야 drop이 온다
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  }

  function handleDragLeave(event: DragEvent<HTMLFormElement>) {
    if (!hasFiles(event)) return;
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setDragging(false);
  }

  function handleDrop(event: DragEvent<HTMLFormElement>) {
    if (!hasFiles(event)) return;
    event.preventDefault();
    dragDepth.current = 0;
    setDragging(false);
    attach(event.dataTransfer.files);
  }

  function removeAttachment() {
    onAttachmentChange(null);
    setError(null);
    attachButtonRef.current?.focus();
  }

  return (
    <div className="flex w-full flex-col gap-1.5">
      <form
        onSubmit={handleSubmit}
        onDragEnter={handleDragEnter}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "relative flex w-full flex-col rounded-field border focus-within:border-blue-500",
          dragging ? "border-blue-500" : "border-grey-300",
        )}
      >
        {dragging && (
          // 끌어 놓는 동안 입력칸 전체를 덮는 안내. 마우스 이벤트는 아래 form이 받는다
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-field bg-blue-50 text-small font-medium text-blue-500"
          >
            <FileText className="size-5" strokeWidth={2} />
            여기에 놓으면 이력서·자기소개서 PDF가 첨부돼요
          </div>
        )}
        {attachment && (
          <div className="flex items-center gap-2.5 border-b border-grey-200 py-2.5 pr-2.5 pl-3">
            <FileText aria-hidden className="size-5 shrink-0 text-grey-600" strokeWidth={2} />
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="truncate text-small font-medium text-grey-900">
                <span className="sr-only">첨부할 파일: </span>
                {attachment.name}
              </p>
              <p className="text-small text-grey-600">{formatSize(attachment.sizeBytes)}</p>
            </div>
            <button
              type="button"
              onClick={removeAttachment}
              aria-label={`${attachment.name} 첨부 빼기`}
              className="flex size-7 shrink-0 items-center justify-center rounded-control text-grey-500 hover:bg-grey-100 hover:text-grey-800"
            >
              <X aria-hidden className="size-4" strokeWidth={2} />
            </button>
          </div>
        )}
        <div className="flex h-13 w-full items-center gap-2 pr-1.75 pl-2">
          <button
            ref={attachButtonRef}
            type="button"
            onClick={() => fileInputRef.current?.click()}
            aria-label={attachment ? "첨부 파일 바꾸기 (이력서·자기소개서 PDF)" : "파일 첨부 (이력서·자기소개서 PDF)"}
            aria-describedby={error ? errorId : undefined}
            className="flex size-9 shrink-0 items-center justify-center rounded-control text-grey-600 hover:bg-grey-100 hover:text-grey-900"
          >
            <Paperclip aria-hidden className="size-5" strokeWidth={2} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept={ATTACHMENT_ACCEPT}
            onChange={handleFile}
            tabIndex={-1}
            aria-hidden
            className="hidden"
          />
          <label htmlFor="mentor-question" className="sr-only">
            AI 멘토에게 보낼 질문
          </label>
          <input
            id="mentor-question"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={attachment ? "파일에 대해 물어볼 내용을 적어 주세요 (비워도 돼요)" : placeholder}
            autoComplete="off"
            className="min-w-0 flex-1 bg-transparent text-body text-grey-900 placeholder:text-grey-500 focus:outline-none"
          />
          <Button type="submit" size="M" disabled={!value.trim() && !attachment}>
            보내기
          </Button>
        </div>
      </form>
      {error && (
        <p id={errorId} role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
