"use client";

import { useSyncExternalStore } from "react";
import { readDevMode, subscribeSession } from "@/lib/session";

/**
 * 개발 모드. 팀이 첫 사용 흐름을 되풀이해 확인할 때 쓰는 표시이고, 인증을 건너뛰지 않는다.
 * 로그인 화면에서 켜면 localStorage(`team07.devMode`)에 남아 소셜 로그인을 다녀와도 유지되고,
 * 로그인이 끝날 때 세션의 `devMode`로 옮겨 적는다. 로그아웃이나 유저 정보 초기화로는 꺼지지 않는다.
 */
const STORAGE_KEY = "team07.devMode";
const CHANGE_EVENT = "team07:devMode";

/** 로그인 화면에서 개발 모드를 켜 두었는지 */
export function readDevModeFlag(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function saveDevModeFlag(enabled: boolean): void {
  if (enabled) window.localStorage.setItem(STORAGE_KEY, "1");
  else window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribeFlag(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) callback();
  };
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", onStorage);
  };
}

/** 로그인 화면의 "개발 모드로 로그인" 체크 상태. 서버 렌더에서는 꺼져 있다. */
export function useDevModeFlag(): boolean {
  return useSyncExternalStore(subscribeFlag, readDevModeFlag, () => false);
}

/** 지금 세션이 개발 모드로 로그인한 세션인지. 로그인 전이거나 서버 렌더면 false. */
export function useDevMode(): boolean {
  return useSyncExternalStore(subscribeSession, readDevMode, () => false);
}
