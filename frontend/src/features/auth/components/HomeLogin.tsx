"use client";

import { useSyncExternalStore } from "react";
import { ArrowLink } from "@/components/ui/ArrowLink";
import { Panel } from "@/components/ui/Panel";
import { readUsername, subscribeSession } from "@/lib/session";
import { SocialLoginButtons } from "./SocialLoginButtons";

/**
 * 홈 맨 위의 로그인 안내. 로그인 전에만 보인다.
 * 정적 HTML에는 세션이 없어서 서버 값은 "모름"(undefined)으로 두고, 브라우저에서 세션을 읽은 뒤에 그린다.
 * 그래야 로그인한 사용자에게 이 상자가 잠깐 보였다 사라지지 않는다.
 */
export function HomeLogin() {
  const username = useSyncExternalStore<string | null | undefined>(subscribeSession, readUsername, () => undefined);
  if (username !== null) return null;

  return (
    <Panel
      as="section"
      aria-labelledby="home-login"
      className="flex w-full flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between"
    >
      <div className="flex flex-col gap-1">
        <h2 id="home-login" className="text-h3 font-bold text-grey-900">
          로그인하고 시작하기
        </h2>
        <p className="text-small text-grey-600">내 프로필에 맞춘 공고와 정책을 볼 수 있어요.</p>
      </div>
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-5">
        <SocialLoginButtons layout="row" next="/" />
        <ArrowLink href="/login/">아이디로 로그인</ArrowLink>
      </div>
    </Panel>
  );
}
