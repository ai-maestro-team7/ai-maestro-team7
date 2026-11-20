"use client";

import { useEffect, useRef } from "react";
import { ChatPanel } from "@/features/chat/components/ChatPanel";
import { playSeagullIntro } from "../intro";
import { BridgeScene } from "./BridgeScene";
import { Seagull } from "./Seagull";

const HEADLINE = "어떤 일을 찾고 있나요?";

/**
 * 홈 첫 화면: 큰 문구와 채팅창 하나만 둔다. 공고·정책 목록은 "채용·정책" 메뉴에서 본다.
 * 배경은 광안대교 3D 장면이고, 제목은 갈매기가 물고 와서 떨어뜨린다 (intro.ts). 등장이 끝난 뒤에는 커서가 지나가는
 * 글자가 물결처럼 떠오른다 (globals.css). 움직임 줄이기 설정이면 등장 없이 바로 보인다.
 */
export function HomeHero() {
  const title = useRef<HTMLHeadingElement>(null);
  const bird = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const titleEl = title.current;
    const birdEl = bird.current;
    if (!titleEl || !birdEl) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      titleEl.dataset.intro = "done";
      return;
    }
    let stop = () => {};
    let cancelled = false;
    // 글자 폭이 정해진 뒤(글꼴을 받은 뒤)에 제자리를 잰다. 글꼴이 늦어도 0.8초 뒤에는 시작한다
    const begin = () => {
      if (cancelled || titleEl.dataset.intro !== "pending") return;
      stop = playSeagullIntro(birdEl, titleEl);
    };
    const timer = window.setTimeout(begin, 800);
    void document.fonts.ready.then(begin);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      stop();
    };
  }, []);

  return (
    <>
      <BridgeScene />
      <Seagull ref={bird} />

      <section className="relative mx-auto flex w-full max-w-main flex-col items-center gap-8 text-center">
        <div className="flex flex-col items-center gap-3">
          <span className="rounded-full bg-white px-3 py-1 text-small font-bold text-blue-500 shadow-sm ring-1 ring-blue-500/15">
            AI 취업 멘토
          </span>
          <h1 ref={title} data-intro="pending" className="hero-title text-title font-bold text-grey-900 xl:text-hero">
            <span className="sr-only">{HEADLINE}</span>
            {/* 글자마다 나눠 등장과 커서 물결을 준다. 화면 읽기 프로그램은 위의 한 줄만 읽는다 */}
            <span aria-hidden className="cursor-default">
              {[...HEADLINE].map((char, index) =>
                char === " " ? (
                  " "
                ) : (
                  <span key={index} className="wave-char">
                    <span className="wave-hop">{char}</span>
                  </span>
                ),
              )}
            </span>
          </h1>
          <p className="text-halo text-body text-grey-700">조건을 말하거나 이력서를 올리면 공고와 청년 정책을 함께 찾아 드려요.</p>
        </div>
        <ChatPanel />
      </section>
    </>
  );
}
