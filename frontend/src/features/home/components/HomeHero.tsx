"use client";

import { type CSSProperties, useEffect, useRef } from "react";
import { ChatPanel } from "@/features/chat/components/ChatPanel";

const HEADLINE = "어떤 일을 찾고 있나요?";

/**
 * 홈 첫 화면: 큰 문구와 채팅창 하나만 둔다. 공고·정책 목록은 "채용·정책" 메뉴에서 본다.
 * 배경은 커서를 따라 옅은 파란 빛과 점 무늬가 움직이고, 제목 글자는 커서가 지나가면 물결처럼 떠오른다 (globals.css).
 * 커서 위치는 렌더링 없이 CSS 변수로만 넣는다. 터치 화면에서는 가만히 있는 빛만 보인다.
 */
export function HomeHero() {
  const backdrop = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = backdrop.current;
    if (!el) return;
    let frame = 0;
    function onMove(event: PointerEvent) {
      if (event.pointerType === "touch") return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (!el) return;
        const box = el.getBoundingClientRect();
        const inside =
          event.clientX >= box.left && event.clientX <= box.right && event.clientY >= box.top && event.clientY <= box.bottom;
        el.style.setProperty("--hero-x", `${event.clientX - box.left}px`);
        el.style.setProperty("--hero-y", `${event.clientY - box.top}px`);
        el.dataset.active = String(inside);
      });
    }
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  return (
    <>
      {/* 배경 (꾸밈): 위쪽 가운데에 늘 있는 옅은 빛 + 커서를 따라오는 빛과 점 무늬 */}
      <div ref={backdrop} aria-hidden data-active="false" className="group/backdrop pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-x-0 -top-24 mx-auto h-110 max-w-220 rounded-full bg-radial from-blue-50 to-transparent to-70% blur-2xl" />
        <div className="hero-glow absolute inset-0 opacity-0 transition-opacity duration-500 group-data-[active=true]/backdrop:opacity-100" />
        <div className="hero-dots absolute inset-0 opacity-0 transition-opacity duration-500 group-data-[active=true]/backdrop:opacity-70" />
      </div>

      <section className="relative mx-auto flex w-full max-w-main flex-col items-center gap-8 text-center">
        <div className="flex flex-col items-center gap-3">
          <span className="rounded-full bg-white px-3 py-1 text-small font-bold text-blue-500 shadow-sm ring-1 ring-blue-500/15">
            AI 취업 멘토
          </span>
          <h1 className="text-title font-bold text-grey-900 xl:text-hero">
            <span className="sr-only">{HEADLINE}</span>
            {/* 글자마다 나눠 커서 물결을 준다. 화면 읽기 프로그램은 위의 한 줄만 읽는다 */}
            <span aria-hidden className="cursor-default">
              {[...HEADLINE].map((char, index) =>
                char === " " ? (
                  " "
                ) : (
                  <span key={index} className="wave-char" style={{ "--i": index } as CSSProperties}>
                    {char}
                  </span>
                ),
              )}
            </span>
          </h1>
          <p className="text-body text-grey-600">조건을 말하거나 이력서를 올리면 공고와 청년 정책을 함께 찾아 드려요.</p>
        </div>
        <ChatPanel />
      </section>
    </>
  );
}
