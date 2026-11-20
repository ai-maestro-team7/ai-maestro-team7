import { ApiError, apiGet, apiSend } from "@/lib/api";
import type { ChatMessage, ChatSessionView, StartResponse } from "./types";

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

/** 답이 COMPLETED·FAILED가 될 때까지 2초마다 조회한다 (docs/api.md §4). */
export async function waitForReply(sessionId: string, messageId: string, signal?: AbortSignal): Promise<ChatMessage> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
    await wait(POLL_INTERVAL_MS, signal);
    const message = await getChatMessage(sessionId, messageId);
    if (message.status === "COMPLETED" || message.status === "FAILED") return message;
  }
  throw new ApiError(408, "POLL_TIMEOUT", "답을 만드는 데 오래 걸리고 있어요. 잠시 뒤 다시 확인해 주세요.", true);
}
