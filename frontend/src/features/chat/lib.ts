import type { InterviewHandoff } from "./types";

const HANDOFF_KEY = "team07.interviewHandoff";
const SESSION_KEY = "team07.chatSessionId";
const HANDOFF_EVENT = "team07:interviewHandoff";

/** 채팅에서 면접 화면으로 넘길 값. 같은 탭 안에서만 쓰도록 sessionStorage에 둔다. */
export function writeHandoff(handoff: InterviewHandoff): void {
  window.sessionStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff));
  window.dispatchEvent(new Event(HANDOFF_EVENT));
}

/** useSyncExternalStore용 스냅샷. 같은 값이면 같은 문자열을 돌려줘야 해서 원문 그대로 준다. */
export function readHandoffRaw(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(HANDOFF_KEY);
}

export function parseHandoff(raw: string | null): InterviewHandoff | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<InterviewHandoff> | null;
    if (!value || value.source !== "chat" || typeof value.job !== "string") return null;
    return {
      job: value.job,
      coverLetter: typeof value.coverLetter === "string" ? value.coverLetter : undefined,
      documentId: typeof value.documentId === "string" ? value.documentId : undefined,
      documentTitle: typeof value.documentTitle === "string" ? value.documentTitle : undefined,
      source: "chat",
    };
  } catch {
    return null;
  }
}

export function subscribeHandoff(onChange: () => void): () => void {
  window.addEventListener(HANDOFF_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(HANDOFF_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** 새로 고침해도 같은 대화를 다시 그리도록 대화 ID만 기억한다 (대화 내용은 서버에 있다). */
export function readChatSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(SESSION_KEY);
}

export function saveChatSessionId(sessionId: string | null): void {
  if (sessionId) window.sessionStorage.setItem(SESSION_KEY, sessionId);
  else window.sessionStorage.removeItem(SESSION_KEY);
}

export function interviewHref(job: string): string {
  return `/interview/?${new URLSearchParams({ job, mode: "voice" }).toString()}`;
}

export const POLICY_STATUS_LABEL: Record<string, string> = {
  ELIGIBLE: "자격이 맞아요",
  CHECK_NEEDED: "확인이 필요해요",
  NOT_ELIGIBLE: "자격이 맞지 않아요",
  AFTER_EMPLOYMENT: "취업하면 받을 수 있어요",
};

export function asOfLabel(value?: string): string | null {
  return value ? `기준 ${value.slice(0, 10)}` : null;
}
