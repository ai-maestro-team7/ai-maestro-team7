"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { createTextDocument, errorMessage, getDocument, poll } from "@/features/mentoring/api";

const MIN_CHARS = 1_000; // A 문서 입력 하한 (mentoring_config.json document.textMinChars)
const MAX_CHARS = 30_000;

/**
 * 이력서 붙여넣기. A 문서 API로 저장하고 역량 추출이 끝나면 문서 ID를 넘긴다.
 * 이력서 원문은 채팅 메시지로 보내지 않는다 (개발계획서4 §2.2).
 */
export function ResumeForm({ onReady, onCancel }: { onReady: (documentId: string) => void; onCancel: () => void }) {
  const [text, setText] = useState("");
  const [state, setState] = useState<"edit" | "reading">("edit");
  const [error, setError] = useState<string>();

  async function submit() {
    const trimmed = text.trim();
    if (trimmed.length < MIN_CHARS || trimmed.length > MAX_CHARS) {
      setError(`이력서는 ${MIN_CHARS.toLocaleString()}~${MAX_CHARS.toLocaleString()}자로 넣어 주세요.`);
      return;
    }
    setError(undefined);
    setState("reading");
    try {
      const created = await createTextDocument(trimmed, "채팅 이력서");
      await poll(() => getDocument(created.documentId));
      onReady(created.documentId);
    } catch (e) {
      setError(errorMessage(e));
      setState("edit");
    }
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-field border border-grey-200 p-4">
      <TextArea
        id="chat-resume"
        label="이력서 붙여넣기"
        value={text}
        rows={8}
        maxLength={MAX_CHARS}
        onChange={(event) => setText(event.target.value)}
        error={error}
        disabled={state === "reading"}
        placeholder="학력, 경험, 프로젝트, 자격증을 붙여 넣어 주세요. 이름·연락처는 빼 주세요"
      />
      <p className="text-small text-grey-600">
        {state === "reading"
          ? "이력서에서 역량을 찾고 있어요. 1분쯤 걸려요."
          : "내 서류함에 저장되고, 찾은 역량은 확인 전 상태로 공고 검색에만 써요."}
      </p>
      <div className="flex gap-2">
        <Button size="M" onClick={submit} disabled={state === "reading" || !text.trim()}>
          {state === "reading" ? "읽는 중" : "이력서로 찾기"}
        </Button>
        <Button size="M" variant="line" onClick={onCancel} disabled={state === "reading"}>
          닫기
        </Button>
      </div>
    </div>
  );
}
