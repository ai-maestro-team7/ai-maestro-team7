import { Suspense } from "react";
import { PageContainer } from "@/components/layout/PageContainer";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { OpenPolicies } from "@/features/policies/components/OpenPolicies";
import { PolicyTableSkeleton } from "@/features/policies/components/PolicyTable";

export default function HomePage() {
  return (
    <PageContainer className="gap-12">
      {/* 화면 제목은 채팅 창 머리말이 맡는다. 문서 제목(h1)은 화면 읽기 프로그램에만 둔다 */}
      <h1 className="sr-only">부산커리어</h1>

      {/* 채팅 창은 본문 폭(700px)으로 가운데에 둬 한 줄이 너무 길어 보이지 않게 한다 */}
      <div className="mx-auto flex w-full max-w-main">
        <ChatPanel />
      </div>

      {/* 맞춤 공고는 "채용·정책 > 맞춤형 공고"에서 본다. 정책은 로그인한 사용자 프로필로 B API에서 읽는다.
          오류 안내가 주소(?q=)를 읽어 Suspense 안에 둔다 */}
      <section aria-labelledby="home-policies" className="flex w-full flex-col gap-3">
        <SectionHeader id="home-policies" title="지금 신청할 수 있는 청년 정책" href="/policies" />
        <Suspense fallback={<PolicyTableSkeleton rows={3} />}>
          <OpenPolicies />
        </Suspense>
      </section>
    </PageContainer>
  );
}
