import type { Metadata } from "next";
import { Suspense } from "react";
import { MentorChat } from "@/features/mentor/components/MentorChat";

export const metadata: Metadata = { title: "AI 멘토" };

/** 대화 목록과 대화가 화면 높이를 채우게 `PageContainer`의 위아래 여백 없이 둔다. */
export default function MentorPage() {
  return (
    <main id="main" className="mx-auto flex w-full max-w-content flex-1 px-5 xl:px-0">
      {/* 고른 대화(?c=)를 주소에서 읽어서 Suspense 경계 안에 둔다 */}
      <Suspense fallback={<div className="h-96 w-full" aria-busy />}>
        <MentorChat />
      </Suspense>
    </main>
  );
}
