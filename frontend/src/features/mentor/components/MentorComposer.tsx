"use client";

import { useState } from "react";
import { Chip } from "@/components/ui/Chip";
import { ATTACHMENT_QUESTION, mentorExamples } from "../data";
import type { MentorAttachment } from "../types";
import { AskBox } from "./AskBox";

type MentorComposerProps = {
  /** 입력칸에 처음 들어 있을 문장 */
  initialDraft?: string;
  placeholder: string;
  /** 다듬은 질문과 붙인 파일 이름을 받는다. 파일 내용은 넘기지 않는다 */
  onSend: (question: string, attachmentName?: string) => void;
};

/**
 * AI 멘토 입력 영역: 입력칸, 예시 질문 Chip, 시연 안내. 홈과 대화 화면이 같이 쓴다.
 * 보내면 입력칸을 비운다. 질문을 어디에 넣고 어디로 갈지는 `onSend`를 받는 쪽이 정한다.
 */
export function MentorComposer({ initialDraft = "", placeholder, onSend }: MentorComposerProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [attachment, setAttachment] = useState<MentorAttachment | null>(null);

  function send(question: string, attached: MentorAttachment | null = null) {
    const trimmed = question.trim() || (attached ? ATTACHMENT_QUESTION : "");
    if (!trimmed) return;
    onSend(trimmed, attached?.name);
    setDraft("");
    setAttachment(null);
  }

  return (
    <div className="flex w-full flex-col gap-3.5">
      <AskBox
        value={draft}
        onChange={setDraft}
        attachment={attachment}
        onAttachmentChange={setAttachment}
        onSubmit={() => send(draft, attachment)}
        placeholder={placeholder}
      />
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-small text-grey-600">예시 질문</p>
        {mentorExamples.map((example) => (
          <Chip key={example.label} onClick={() => send(example.question)}>
            {example.label}
          </Chip>
        ))}
      </div>
      <p className="text-small text-grey-600">
        시연 모드에서는 준비된 답변을 보여드려요. 이력서·자기소개서 PDF를 클립 버튼으로 고르거나 입력칸에 끌어다
        놓을 수 있어요 (10MB 이하).
      </p>
    </div>
  );
}
