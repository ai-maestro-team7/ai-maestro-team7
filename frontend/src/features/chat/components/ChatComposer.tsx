"use client";

import { Square } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useLayoutEffect, useRef } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { AttachButton } from "./PdfAttach";

/** 입력칸이 커지는 최대 높이 (약 6줄) */
const MAX_HEIGHT_PX = 168;

/**
 * 채팅 화면 아래 입력칸. Enter로 보내고 Shift+Enter로 줄을 바꾼다 (한글 조합 중 Enter는 보내지 않는다).
 * 답을 만드는 동안에는 보내기 자리에 멈추기 버튼이 온다.
 *
 * suggestion이 있고 입력칸이 비어 있으면 그 문장을 반투명하게 보여 준다. Tab(또는 오른쪽 [Tab] 단추)을 누르면
 * 입력칸에 채워지고, Enter를 누르면 바로 보낸다. Esc를 누르면 이번 추천을 숨긴다.
 */
export function ChatComposer({
  value,
  onChange,
  onSubmit,
  onStop,
  generating,
  stopping,
  disabled,
  suggestion,
  onDismissSuggestion,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  /** 답을 만드는 중. 보내기 대신 멈추기를 보여 준다 */
  generating: boolean;
  /** 멈추기 요청을 보내는 중 */
  stopping: boolean;
  disabled: boolean;
  /** 반투명 추천 문장. 입력칸이 비어 있을 때만 보인다 */
  suggestion?: string | null;
  onDismissSuggestion?: () => void;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // 글 길이에 맞춰 높이를 바꾼다
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [value]);

  function submit() {
    if (!disabled && !generating && value.trim()) onSubmit();
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    submit();
  }

  const ghost = !value && !disabled && !generating ? (suggestion ?? null) : null;

  function acceptSuggestion() {
    if (!ghost) return;
    onChange(ghost);
    ref.current?.focus();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (ghost && !event.nativeEvent.isComposing && !event.shiftKey && event.key === "Tab") {
      event.preventDefault();
      acceptSuggestion();
      return;
    }
    if (ghost && event.key === "Escape") {
      event.preventDefault();
      onDismissSuggestion?.();
      return;
    }
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full items-end gap-2 rounded-field border border-grey-300 bg-white p-1.75 focus-within:border-blue-500"
    >
      <AttachButton disabled={disabled || generating} />
      <label htmlFor="chat-input" className="sr-only">
        AI 멘토에게 보낼 말
      </label>
      <textarea
        id="chat-input"
        ref={ref}
        rows={1}
        value={value}
        maxLength={1000}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={ghost ?? "조건을 말하거나 궁금한 점을 물어보세요"}
        aria-describedby={ghost ? "chat-suggestion-hint" : undefined}
        className={cn(
          "min-h-9.5 flex-1 resize-none bg-transparent py-1.75 text-body text-grey-900 focus:outline-none",
          ghost ? "placeholder:text-grey-400" : "placeholder:text-grey-500",
        )}
      />
      {ghost && (
        <>
          <span id="chat-suggestion-hint" className="sr-only">
            Tab 키를 누르면 추천 문장이 입력칸에 채워지고, Enter 키로 보낼 수 있어요. Esc 키로 추천을 숨겨요.
          </span>
          <button
            type="button"
            onClick={acceptSuggestion}
            tabIndex={-1}
            className="mb-1.5 shrink-0 rounded-control border border-grey-300 px-1.5 py-0.5 text-small font-medium text-grey-500 hover:bg-grey-50"
          >
            Tab
            <span className="sr-only"> 추천 문장 채우기</span>
          </button>
        </>
      )}
      {generating ? (
        <Button type="button" size="M" variant="secondary" onClick={onStop} disabled={stopping} className="gap-1.5">
          <Square aria-hidden className="size-3 fill-current" strokeWidth={2.5} />
          {stopping ? "멈추는 중" : "멈추기"}
        </Button>
      ) : (
        <Button type="submit" size="M" disabled={disabled || !value.trim()}>
          보내기
        </Button>
      )}
    </form>
  );
}
