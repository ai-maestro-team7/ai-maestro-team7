import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { HeroCards } from "./HeroCards";

/**
 * 홈 첫 화면: 큰 문구와 채팅창 하나만 둔다. 공고·정책 목록은 "채용·정책" 메뉴에서 본다.
 * 위쪽 가운데의 옅은 파란 빛과 양옆 카드(넓은 화면에서만)는 꾸밈이다. 색은 디자인 토큰만 쓴다.
 */
export function HomeHero() {
  return (
    <section className="relative isolate w-full">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-16 -z-10 mx-auto h-105 max-w-200 rounded-full bg-radial from-blue-50 to-transparent to-70% blur-2xl"
      />
      <HeroCards />
      <div className="relative mx-auto flex w-full max-w-main flex-col items-center gap-8 pt-4 pb-6 text-center xl:pt-10 xl:pb-12">
        <div className="flex flex-col items-center gap-3">
          <span className="rounded-full bg-blue-50 px-3 py-1 text-small font-bold text-blue-500">AI 취업 멘토</span>
          <h1 className="text-title font-bold text-grey-900 xl:text-hero">어떤 일을 찾고 있나요?</h1>
          <p className="text-body text-grey-600">조건을 말하거나 이력서를 올리면 공고와 청년 정책을 함께 찾아 드려요.</p>
        </div>
        <ChatPanel />
      </div>
    </section>
  );
}
