import { FileText } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { MentorMessage } from "../types";

/**
 * 대화 내용 (Figma 홈 · AI 멘토 답변). 내 질문은 오른쪽 회색 말풍선, 답변은 "AI 멘토" 아래 왼쪽 글이다.
 * 브라우저에 보관했던 글이므로 모두 글자로만 넣는다.
 */
export function MentorThread({ messages }: { messages: MentorMessage[] }) {
  return (
    <ol aria-live="polite" className="flex flex-col gap-6">
      {messages.map((message, index) =>
        message.role === "user" ? (
          <li key={index} className="flex max-w-[85%] flex-col items-end gap-2 self-end">
            {message.attachmentName && <AttachmentCard name={message.attachmentName} />}
            <p className="rounded-card bg-grey-100 px-3.5 py-2.5 text-body break-words text-grey-900">
              <span className="sr-only">내 질문: </span>
              {message.question}
            </p>
          </li>
        ) : (
          <li key={index} className="flex flex-col gap-2.5">
            <p className="text-small font-bold text-grey-600">AI 멘토</p>
            <p className="text-body text-grey-900">{message.answer}</p>
            {message.recommendations?.map((recommendation) => (
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
          </li>
        ),
      )}
    </ol>
  );
}

/** 보낸 질문 위에 보이는 첨부 파일 카드. 파일은 보관하지 않아 이름만 보여준다 */
function AttachmentCard({ name }: { name: string }) {
  return (
    <p className="flex max-w-full items-center gap-2.5 rounded-field border border-grey-200 bg-white py-2.5 pr-3.5 pl-3">
      <FileText aria-hidden className="size-5 shrink-0 text-grey-600" strokeWidth={2} />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-small font-medium text-grey-900">
          <span className="sr-only">첨부 파일: </span>
          {name}
        </span>
        <span className="text-small text-grey-600">PDF</span>
      </span>
    </p>
  );
}
