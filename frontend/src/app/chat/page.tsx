import type { Metadata } from "next";
import { Suspense } from "react";
import { ChatWorkspace } from "@/features/chat/components/ChatWorkspace";

export const metadata: Metadata = { title: "AI 멘토와 채팅" };

/** 채팅 Agent 화면. 대화 목록과 대화가 화면 높이를 채우게 `PageContainer`의 위아래 여백 없이 둔다 (`/mentor/`와 같은 틀). */
export default function ChatPage() {
  return (
    <main id="main" className="mx-auto flex w-full max-w-content flex-1 flex-col px-5 lg:flex-row xl:px-0">
      {/* 고른 대화(?s=)를 주소에서 읽어서 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<div className="h-96 w-full" aria-busy />}>
        <ChatWorkspace />
      </Suspense>
    </main>
  );
}
