"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api";
import { deleteChatSession, listChatSessions, setChatPinned } from "./api";
import type { ChatSessionSummary } from "./types";

export type SessionsState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; sessions: ChatSessionSummary[] };

function errorText(error: unknown): string {
  return error instanceof ApiError ? error.message : "대화 목록을 불러오지 못했어요.";
}

/** 서버와 같은 순서: 고정한 대화가 먼저, 그 안과 밖은 최근에 말한 순서 */
function ordered(sessions: ChatSessionSummary[]): ChatSessionSummary[] {
  return [...sessions].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned) || b.lastMessageAt.localeCompare(a.lastMessageAt),
  );
}

/**
 * 채팅 화면 왼쪽의 대화 목록. 고정은 화면을 먼저 바꾸고 서버 응답으로 다시 맞춘다.
 * 다시 불러오다 실패하면 갖고 있던 목록을 그대로 둔다.
 */
export function useChatSessions() {
  const [state, setState] = useState<SessionsState>({ status: "loading" });
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    listChatSessions().then(
      (body) => active && setState({ status: "ready", sessions: body.sessions }),
      (error: unknown) =>
        active && setState((prev) => (prev.status === "ready" ? prev : { status: "error", message: errorText(error) })),
    );
    return () => {
      active = false;
    };
  }, [version]);

  const reload = useCallback(() => setVersion((n) => n + 1), []);

  const update = useCallback((change: (sessions: ChatSessionSummary[]) => ChatSessionSummary[]) => {
    setState((prev) => (prev.status === "ready" ? { status: "ready", sessions: ordered(change(prev.sessions)) } : prev));
  }, []);

  /** 고정·고정 해제. 실패하면 서버 목록으로 되돌리고 오류를 던진다 */
  const pin = useCallback(
    async (sessionId: string, pinned: boolean) => {
      update((sessions) => sessions.map((s) => (s.sessionId === sessionId ? { ...s, pinned } : s)));
      try {
        await setChatPinned(sessionId, pinned);
      } finally {
        reload();
      }
    },
    [reload, update],
  );

  /** 지우기. 서버가 지운 뒤에 목록에서 뺀다 */
  const remove = useCallback(
    async (sessionId: string) => {
      await deleteChatSession(sessionId);
      update((sessions) => sessions.filter((s) => s.sessionId !== sessionId));
      reload();
    },
    [reload, update],
  );

  return { state, reload, pin, remove };
}
