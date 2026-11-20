import { ApiError, apiGet, apiSend } from "@/lib/api";
import type { ChatMessage, ChatSessionSummary, ChatSessionView, StartResponse } from "./types";

const POLL_INTERVAL_MS = 2_000;
const POLL_TIMEOUT_MS = 120_000;

/** `POST /api/v1/agent/chat` → 202. 답은 `waitForReply`로 받는다. */
export function sendChat(body: {
  sessionId?: string;
  message: string;
  attachments?: { documentId: string }[];
}): Promise<StartResponse> {
  return apiSend<StartResponse>("POST", "/api/v1/agent/chat", body);
}

export function getChatMessage(sessionId: string, messageId: string): Promise<ChatMessage> {
  return apiGet<ChatMessage>(
    `/api/v1/agent/chat/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}`,
  );
}

export function getChatSession(sessionId: string): Promise<ChatSessionView> {
  return apiGet<ChatSessionView>(`/api/v1/agent/chat/${encodeURIComponent(sessionId)}`);
}

/** 내 대화 목록 (메시지 없이) */
export function listChatSessions(): Promise<{ sessions: ChatSessionSummary[] }> {
  return apiGet<{ sessions: ChatSessionSummary[] }>("/api/v1/agent/chat");
}

/** `apiSend`의 메서드 목록에 PATCH가 없어 같은 함수를 PATCH로 부른다. 토큰 갱신과 오류 처리는 그대로 쓴다 */
function apiPatch<T>(path: string, body: object): Promise<T> {
  const send = apiSend as unknown as (method: string, path: string, body?: object) => Promise<T>;
  return send("PATCH", path, body);
}

/** 대화 고정·고정 해제. 응답은 대화 (메시지 없이) */
export function setChatPinned(sessionId: string, pinned: boolean): Promise<ChatSessionSummary> {
  return apiPatch<ChatSessionSummary>(`/api/v1/agent/chat/${encodeURIComponent(sessionId)}`, { pinned });
}

/** 대화와 메시지를 모두 지운다 */
export function deleteChatSession(sessionId: string): Promise<{ sessionId: string; deleted: boolean }> {
  return apiSend("DELETE", `/api/v1/agent/chat/${encodeURIComponent(sessionId)}`);
}

/** 만드는 중인 답을 멈춘다. 그사이 답이 끝났으면 끝난 답이 온다 */
export function cancelChatMessage(sessionId: string, messageId: string): Promise<ChatMessage> {
  return apiSend<ChatMessage>(
    "POST",
    `/api/v1/agent/chat/${encodeURIComponent(sessionId)}/messages/${encodeURIComponent(messageId)}/cancel`,
  );
}

/** 답이 더 바뀌지 않는 상태 */
export function isSettled(message: ChatMessage): boolean {
  return message.status === "COMPLETED" || message.status === "FAILED" || message.status === "CANCELLED";
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timer);
        reject(new DOMException("요청이 취소됐어요.", "AbortError"));
      },
      { once: true },
    );
  });
}

/** 답이 COMPLETED·FAILED·CANCELLED가 될 때까지 2초마다 조회한다 (docs/api.md §4). `signal`로 조회를 멈춘다 */
export async function waitForReply(sessionId: string, messageId: string, signal?: AbortSignal): Promise<ChatMessage> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
    await wait(POLL_INTERVAL_MS, signal);
    const message = await getChatMessage(sessionId, messageId);
    if (isSettled(message)) return message;
  }
  throw new ApiError(408, "POLL_TIMEOUT", "답을 만드는 데 오래 걸리고 있어요. 잠시 뒤 다시 확인해 주세요.", true);
}
