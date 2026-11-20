"use client";

import { useRouter } from "next/navigation";
import { ArrowLink } from "@/components/ui/ArrowLink";
import { startConversation, useConversations } from "../conversations";
import { MENTOR_DEFAULT_QUESTION } from "../data";
import { mentorChatHref } from "../lib";
import { MentorComposer } from "./MentorComposer";

/**
 * 홈 "AI 멘토에게 물어보기" (Figma 홈). 질문을 보내면 새 대화를 만들어 대화 화면(`/mentor/?c=`)으로 간다.
 * 답변은 대화 화면이 붙이고 여기서는 보여주지 않는다. 나눈 대화가 있으면 가장 최근 대화로 가는 링크를 둔다.
 */
export function MentorPanel() {
  const router = useRouter();
  const latest = useConversations().at(0);

  function handleSend(question: string, attachmentName?: string) {
    router.push(mentorChatHref(startConversation(question, attachmentName)));
  }

  return (
    <section aria-labelledby="mentor-title" className="flex min-w-0 flex-1 flex-col gap-3.5">
      <div className="flex items-center justify-between gap-3">
        <h2 id="mentor-title" className="text-h3 font-bold text-grey-900">
          AI 멘토에게 물어보기
        </h2>
        {latest && <ArrowLink href={mentorChatHref(latest.id)}>이전 대화 보기</ArrowLink>}
      </div>
      <MentorComposer
        initialDraft={MENTOR_DEFAULT_QUESTION}
        placeholder="궁금한 점을 물어보세요"
        onSend={handleSend}
      />
    </section>
  );
}
