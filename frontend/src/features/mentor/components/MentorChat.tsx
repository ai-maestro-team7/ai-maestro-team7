"use client";

import { Trash2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { cn } from "@/lib/cn";
import { addQuestion, addReply, deleteConversation, startConversation, useConversations } from "../conversations";
import { mentorReplyTo } from "../data";
import { mentorChatHref } from "../lib";
import type { MentorConversation } from "../types";
import { MentorComposer } from "./MentorComposer";
import { MentorThread } from "./MentorThread";

/**
 * AI 멘토 대화 화면. 왼쪽은 대화 목록, 오른쪽은 고른 대화(`?c=`)와 아래에 붙어 있는 입력칸이다.
 * `?c=`가 없으면 새 대화다. 답변은 홈에서 쓰던 시연 답변을 그대로 쓰고 네트워크 요청을 보내지 않는다.
 */
export function MentorChat() {
  const router = useRouter();
  const conversationId = useSearchParams().get("c");
  const conversations = useConversations();
  const active = conversations.find((conversation) => conversation.id === conversationId);
  const [deleting, setDeleting] = useState<MentorConversation | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const activeId = active?.id;
  const last = active?.messages.at(-1);
  const messageCount = active?.messages.length ?? 0;

  // 홈에서 넘어온 첫 질문이나 여기서 보낸 질문처럼, 마지막 글이 질문이면 답을 붙인다
  useEffect(() => {
    if (activeId && last?.role === "user") {
      addReply(activeId, mentorReplyTo(last.question, last.attachmentName !== undefined));
    }
  }, [activeId, last]);

  // 대화를 열거나 글이 늘면 입력칸이 화면 아래에 오게 내린다
  useEffect(() => {
    if (messageCount > 0) endRef.current?.scrollIntoView({ block: "end" });
  }, [activeId, messageCount]);

  function handleSend(question: string, attachmentName?: string) {
    if (activeId) addQuestion(activeId, question, attachmentName);
    else router.push(mentorChatHref(startConversation(question, attachmentName)));
  }

  function handleDelete(conversation: MentorConversation) {
    deleteConversation(conversation.id);
    setDeleting(null);
    if (conversation.id === conversationId) router.replace(mentorChatHref());
  }

  return (
    <>
      <aside
        aria-label="대화 목록"
        className="sticky top-0 flex max-h-dvh w-65 shrink-0 flex-col gap-5 self-start overflow-y-auto py-6 pr-4"
      >
        <Button href={mentorChatHref()} variant="line" size="M" fullWidth>
          새 대화
        </Button>
        <div className="flex flex-col gap-1.5">
          <h2 className="px-2.5 text-small font-medium text-grey-600">대화 기록</h2>
          {conversations.length === 0 ? (
            <p className="px-2.5 text-small text-grey-500">아직 나눈 대화가 없어요.</p>
          ) : (
            <ul className="flex flex-col gap-0.5">
              {conversations.map((conversation) => {
                const current = conversation.id === activeId;
                return (
                  <li key={conversation.id} className="group relative">
                    <Link
                      href={mentorChatHref(conversation.id)}
                      aria-current={current ? "page" : undefined}
                      className={cn(
                        "block truncate rounded-control py-2 pr-9 pl-2.5 text-small",
                        current ? "bg-grey-100 font-medium text-grey-900" : "text-grey-800 hover:bg-grey-50",
                      )}
                    >
                      {conversation.title}
                    </Link>
                    <button
                      type="button"
                      onClick={() => setDeleting(conversation)}
                      aria-label={`${conversation.title} 대화 지우기`}
                      className="absolute top-1/2 right-1 flex size-7 -translate-y-1/2 items-center justify-center rounded-control text-grey-500 opacity-0 group-hover:opacity-100 hover:bg-grey-200 hover:text-grey-800 focus-visible:opacity-100"
                    >
                      <Trash2 aria-hidden className="size-4" strokeWidth={2} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col border-l border-grey-200 pl-8">
        <div className="flex flex-1 flex-col gap-6 pt-6 pb-8">
          {active ? (
            <>
              {/* 제목은 첫 질문과 같은 글이라 화면에는 보이지 않게 둔다 */}
              <h1 className="sr-only">{active.title}</h1>
              <MentorThread messages={active.messages} />
            </>
          ) : conversationId ? (
            <div className="flex flex-col gap-1">
              <h1 className="text-h3 font-bold text-grey-900">대화를 찾지 못했어요</h1>
              <p className="text-body text-grey-700">
                지웠거나 다른 계정으로 나눈 대화일 수 있어요. 아래에서 새로 물어볼 수 있어요.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-1">
              <h1 className="text-h3 font-bold text-grey-900">새 대화</h1>
              <p className="text-body text-grey-700">아래 입력칸에 질문을 적거나 예시 질문을 눌러 보세요.</p>
            </div>
          )}
        </div>
        <div className="sticky bottom-0 bg-white pt-2 pb-6">
          <MentorComposer placeholder={active ? "이어서 물어보세요" : "궁금한 점을 물어보세요"} onSend={handleSend} />
        </div>
        <div ref={endRef} />
      </div>

      {deleting && (
        <Dialog
          title="이 대화를 지울까요?"
          onClose={() => setDeleting(null)}
          actions={
            <>
              <Button variant="line" size="M" onClick={() => setDeleting(null)}>
                취소
              </Button>
              <Button size="M" onClick={() => handleDelete(deleting)}>
                대화 지우기
              </Button>
            </>
          }
        >
          <p className="break-words">{deleting.title}</p>
          <p>지운 대화는 되돌릴 수 없어요.</p>
        </Dialog>
      )}
    </>
  );
}
