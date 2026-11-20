"use client";

import { useSyncExternalStore } from "react";
import { safeNextPath } from "@/features/auth/lib";
import { readSession, sessionOwner, subscribeSession } from "@/lib/session";
import type { MentorConversation, MentorMessage, MentorRecommendation, MentorReply } from "./types";

/**
 * AI 멘토 대화 기록. 대화를 저장하는 API가 없어 브라우저 localStorage에 둔다.
 * 키는 사용자마다 다르다 (`team07.mentorChats.<sub>`, 로그인 전에는 `team07.mentorChats.anonymous`).
 * 로그아웃해도 지우지 않아서 같은 브라우저로 다시 로그인하면 그대로 보이고, 다른 사용자에게는 보이지 않는다.
 * 파일 내용은 넣지 않는다 (붙인 파일은 이름만 남는다).
 */
const KEY_PREFIX = "team07.mentorChats";
const CHANGE_EVENT = "team07:mentorChats";

/** 대화는 최근 50개까지, 한 대화의 글은 최근 200건까지 둔다. 넘치면 오래된 것부터 버린다. */
const MAX_CONVERSATIONS = 50;
const MAX_MESSAGES = 200;
const TITLE_LENGTH = 40;

const EMPTY: MentorConversation[] = [];

function storageKey(): string {
  const session = readSession();
  return `${KEY_PREFIX}.${session ? sessionOwner(session) : "anonymous"}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function toRecommendation(value: unknown): MentorRecommendation | null {
  if (!isRecord(value)) return null;
  const { title, meta, actionLabel, href } = value;
  if (typeof title !== "string" || typeof meta !== "string" || typeof actionLabel !== "string") return null;
  // 저장된 값이 바뀌어 있어도 사이트 안 경로로만 보낸다
  if (typeof href !== "string" || safeNextPath(href) !== href) return null;
  return { title, meta, actionLabel, href };
}

function toMessage(value: unknown): MentorMessage | null {
  if (!isRecord(value)) return null;
  if (value.role === "user" && typeof value.question === "string") {
    const attachmentName = typeof value.attachmentName === "string" ? value.attachmentName : undefined;
    return { role: "user", question: value.question, ...(attachmentName ? { attachmentName } : {}) };
  }
  if (value.role === "assistant" && typeof value.answer === "string") {
    const recommendations = Array.isArray(value.recommendations)
      ? value.recommendations.map(toRecommendation).filter((item) => item !== null)
      : [];
    return { role: "assistant", answer: value.answer, ...(recommendations.length ? { recommendations } : {}) };
  }
  return null;
}

function toConversation(value: unknown): MentorConversation | null {
  if (!isRecord(value)) return null;
  const { id, title, updatedAt } = value;
  if (typeof id !== "string" || typeof title !== "string" || typeof updatedAt !== "number") return null;
  const messages = Array.isArray(value.messages) ? value.messages.map(toMessage).filter((item) => item !== null) : [];
  return messages.length ? { id, title, updatedAt, messages } : null;
}

/** 저장된 글을 읽는다. JSON이 깨졌거나 모양이 다른 항목은 버리고 읽을 수 있는 대화만 남긴다. */
function parse(raw: string | null): MentorConversation[] {
  if (!raw) return EMPTY;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return EMPTY;
    const conversations = parsed.map(toConversation).filter((item) => item !== null);
    return conversations.length ? conversations.sort((a, b) => b.updatedAt - a.updatedAt) : EMPTY;
  } catch {
    return EMPTY;
  }
}

/** `useSyncExternalStore`가 같은 배열을 받게, 저장된 글이 바뀌지 않았으면 전에 읽은 결과를 그대로 준다. */
let snapshot: { key: string; raw: string | null; conversations: MentorConversation[] } | null = null;

/** 지금 사용자의 대화. 최근에 글이 오간 대화가 앞에 온다. */
export function readConversations(): MentorConversation[] {
  const key = storageKey();
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    // 저장소를 쓸 수 없는 브라우저 설정이면 기록 없이 쓴다
  }
  if (snapshot?.key !== key || snapshot.raw !== raw) snapshot = { key, raw, conversations: parse(raw) };
  return snapshot.conversations;
}

function store(key: string, conversations: MentorConversation[]): boolean {
  try {
    if (conversations.length === 0) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, JSON.stringify(conversations));
    return true;
  } catch {
    return false;
  }
}

function write(conversations: MentorConversation[]): void {
  const key = storageKey();
  let kept = conversations.slice(0, MAX_CONVERSATIONS);
  // 저장 공간이 모자라면 오래된 대화부터 하나씩 덜어 내고 다시 쓴다
  while (!store(key, kept) && kept.length > 1) kept = kept.slice(0, -1);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function userMessage(question: string, attachmentName?: string): MentorMessage {
  return { role: "user", question, ...(attachmentName ? { attachmentName } : {}) };
}

function titleOf(question: string): string {
  const oneLine = question.replace(/\s+/g, " ").trim();
  return oneLine.length > TITLE_LENGTH ? `${oneLine.slice(0, TITLE_LENGTH)}…` : oneLine;
}

function update(id: string, change: (messages: MentorMessage[]) => MentorMessage[]): void {
  const conversations = readConversations();
  const target = conversations.find((conversation) => conversation.id === id);
  if (!target) return;
  const messages = change(target.messages);
  if (messages === target.messages) return;
  write([
    { ...target, updatedAt: Date.now(), messages: messages.slice(-MAX_MESSAGES) },
    ...conversations.filter((conversation) => conversation !== target),
  ]);
}

/** 새 대화를 만들어 첫 질문을 넣고 대화 ID를 준다. 답은 대화 화면이 붙인다. */
export function startConversation(question: string, attachmentName?: string): string {
  const id = crypto.randomUUID();
  write([
    { id, title: titleOf(question), updatedAt: Date.now(), messages: [userMessage(question, attachmentName)] },
    ...readConversations(),
  ]);
  return id;
}

export function addQuestion(id: string, question: string, attachmentName?: string): void {
  update(id, (messages) => [...messages, userMessage(question, attachmentName)]);
}

/** 마지막 글이 아직 답을 받지 못한 질문일 때만 답을 붙인다. 같은 질문에 두 번 답하지 않는다. */
export function addReply(id: string, reply: MentorReply): void {
  update(id, (messages) =>
    messages.at(-1)?.role === "user" ? [...messages, { role: "assistant", ...reply }] : messages,
  );
}

export function deleteConversation(id: string): void {
  write(readConversations().filter((conversation) => conversation.id !== id));
}

/** 지금 사용자의 대화를 모두 지운다 (개발 모드의 유저 정보 초기화). */
export function clearConversations(): void {
  write([]);
}

function subscribe(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key.startsWith(KEY_PREFIX)) callback();
  };
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", onStorage);
  // 로그인·로그아웃하면 키가 바뀌어 보이는 대화도 바뀐다
  const unsubscribeSession = subscribeSession(callback);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", onStorage);
    unsubscribeSession();
  };
}

/** 지금 사용자의 대화 목록. 정적 HTML(서버 렌더)에는 저장소가 없으므로 서버 값은 빈 목록이다. */
export function useConversations(): MentorConversation[] {
  return useSyncExternalStore(subscribe, readConversations, () => EMPTY);
}
