"use client";

import { useSyncExternalStore } from "react";
import { readUsername, subscribeSession } from "@/lib/session";

/**
 * 로그인한 아이디. 로그인 전이면 null.
 * 정적 HTML(서버 렌더)에는 세션이 없으므로 서버 값은 null이다.
 */
export function useUsername(): string | null {
  return useSyncExternalStore(subscribeSession, readUsername, () => null);
}
