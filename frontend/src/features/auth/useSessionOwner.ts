"use client";

import { useSyncExternalStore } from "react";
import { sessionOwner, subscribeSession } from "@/lib/session";

/**
 * 로그인한 사용자의 고유 ID(토큰 sub). 로그인 전이면 null.
 * 아이디(`useUsername`)는 소셜 로그인끼리 "Google 계정"처럼 같을 수 있어 사용자별 화면 상태는 이 값으로 나눈다.
 */
export function useSessionOwner(): string | null {
  return useSyncExternalStore(subscribeSession, () => sessionOwner(), () => null);
}
