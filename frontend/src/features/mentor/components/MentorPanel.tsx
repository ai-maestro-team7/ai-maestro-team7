"use client";

import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { FOLLOW_UP_EXAMPLE_LABEL, findMentorReply, MENTOR_DEFAULT_QUESTION, mentorExamples } from "../data";
import type { MentorExample, MentorTurn } from "../types";

/**
 * 홈 "AI 멘토에게 물어보기". 처음에는 입력 화면(Figma 홈), 질문을 보내면 대화 화면(Figma 홈 · AI 멘토 답변)으로 바뀐다.
 * 답변은 Mock 데이터에서 고르며 네트워크 요청을 보내지 않는다.
 */
export function MentorPanel() {
  const [turns, setTurns] = useState<MentorTurn[]>([]);
  const [draft, setDraft] = useState(MENTOR_DEFAULT_QUESTION);

  function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed) return;
    setTurns((prev) => [...prev, { question: trimmed, reply: findMentorReply(trimmed) }]);
    setDraft("");
  }

  function reset() {
    setTurns([]);
    setDraft(MENTOR_DEFAULT_QUESTION);
  }

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
                <p className="max-w-[85%] self-end rounded-card bg-grey-100 px-3.5 py-2.5 text-body text-grey-900">
                  <span className="sr-only">내 질문: </span>
                  {turn.question}
                </p>
                <div className="flex flex-col gap-2.5">
                  <p className="text-small font-bold text-grey-600">AI 멘토</p>
                  <p className="text-body text-grey-900">{turn.reply.answer}</p>
                  {turn.reply.recommendation && (
                    <div className="flex items-center justify-between gap-3 rounded-field border border-grey-200 py-3 pr-3.5 pl-4">
                      <div className="flex min-w-0 flex-col gap-0.5">
                        <p className="text-body font-bold text-grey-900">{turn.reply.recommendation.title}</p>
                        <p className="text-small text-grey-600">{turn.reply.recommendation.meta}</p>
                      </div>
                      <Button href={turn.reply.recommendation.href} variant="line" size="M">
                        {turn.reply.recommendation.actionLabel}
                      </Button>
                    </div>
                  )}
                  <p className="text-small text-grey-600">시연용 답변이에요.</p>
                </div>
              </li>
            ))}
          </ol>
          <div className="flex flex-wrap gap-2">
            <Chip onClick={reset}>새 질문</Chip>
            {followUpExample && <ExampleChip example={followUpExample} onAsk={ask} />}
          </div>
          <AskBox value={draft} onChange={setDraft} onSubmit={() => ask(draft)} placeholder="이어서 물어보세요" />
        </div>
      ) : (
        <>
          <AskBox value={draft} onChange={setDraft} onSubmit={() => ask(draft)} placeholder="궁금한 점을 물어보세요" />
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-small text-grey-600">예시 질문</p>
            {mentorExamples.map((example) => (
              <ExampleChip key={example.label} example={example} onAsk={ask} />
            ))}
          </div>
          <p className="text-small text-grey-600">시연 모드에서는 준비된 답변을 보여드려요.</p>
        </>
      )}
    </section>
  );
}

function ExampleChip({ example, onAsk }: { example: MentorExample; onAsk: (question: string) => void }) {
  return <Chip onClick={() => onAsk(example.question)}>{example.label}</Chip>;
}

function AskBox({
  value,
  onChange,
  onSubmit,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  placeholder: string;
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex h-13 w-full items-center gap-3 rounded-field border border-grey-300 pr-1.75 pl-4 focus-within:border-blue-500"
    >
      <label htmlFor="mentor-question" className="sr-only">
        AI 멘토에게 보낼 질문
      </label>
      <input
        id="mentor-question"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="min-w-0 flex-1 bg-transparent text-body text-grey-900 placeholder:text-grey-500 focus:outline-none"
      />
      <Button type="submit" size="M" disabled={!value.trim()}>
        보내기
      </Button>
    </form>
  );
}
