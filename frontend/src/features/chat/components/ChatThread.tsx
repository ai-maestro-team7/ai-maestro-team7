"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { Skeleton, SkeletonGroup } from "@/components/ui/Skeleton";
import { ApiError } from "@/lib/api";
import { cancelChatMessage, getChatSession, isSettled, sendChat, waitForReply } from "../api";
import { CHAT_EXAMPLES, interviewSuggestion } from "../lib";
import type { ChatMessage } from "../types";
import { ChatComposer } from "./ChatComposer";
import { AssistantMessage, POLL_FAILED, UserBubble } from "./ChatMessages";
import { PdfDropZone } from "./PdfAttach";
import { ResumeForm } from "./ResumeForm";

const PENDING_ID = "pending";

/**
 * 새 대화의 첫 턴을 보낸 뒤 주소가 `?s=`로 바뀌면 대화 칸을 새로 그린다. 그때 서버에서 다시 읽기 전에도
 * 같은 글을 바로 보여 주려고 넘기는 값이다. 새 대화 칸은 서버 글을 다시 읽어 맞춘다.
 */
export type ThreadSeed = { sessionId: string; messages: ChatMessage[]; pendingId: string | null };

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function lastPending(messages: ChatMessage[]): ChatMessage | undefined {
  return [...messages]
    .reverse()
    .find((m) => m.role === "ASSISTANT" && (m.status === "PENDING" || m.status === "PROCESSING"));
}

/**
 * 대화 하나와 아래 입력칸. 답을 만드는 동안 보내기 자리에 멈추기 버튼이 오고, 누르면 조회를 멈추고 서버에 멈춤을 알린다.
 * 대화를 바꾸면 이 칸을 새로 만든다(key). 칸을 떠나도 서버의 답 만들기는 계속되고, 다시 열면 이어서 기다린다.
 */
export function ChatThread({
  sessionId,
  seed,
  onCreated,
  onChanged,
}: {
  /** 주소의 대화 ID. 없으면 새 대화 */
  sessionId: string | null;
  seed: ThreadSeed | null;
  /** 새 대화의 첫 턴을 보냈다. 화면이 주소를 바꾼다 */
  onCreated: (seed: ThreadSeed) => void;
  /** 대화 목록을 다시 읽을 때 (보냄, 답이 옴, 멈춤) */
  onChanged: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>(seed?.messages ?? []);
  const [view, setView] = useState<"loading" | "ready" | "missing" | "error">(sessionId && !seed ? "loading" : "ready");
  const [title, setTitle] = useState<string | null>(null);
  const [currentId, setCurrentId] = useState<string | null>(sessionId);
  const [pendingId, setPendingId] = useState<string | null>(seed?.pendingId ?? null);
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [stopError, setStopError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  /** Esc로 숨긴 추천의 답 ID. 다음 답이 오면 다시 추천한다 */
  const [hiddenSuggestionFor, setHiddenSuggestionFor] = useState<string | null>(null);
  const [resumeOpen, setResumeOpen] = useState(false);
  // 서류를 올려 글자·역량을 찾는 중. 이때 보내면 끝난 서류가 대화에 붙지 못하므로 보내기를 막는다
  const [docBusy, setDocBusy] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);
  const poller = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const generating = pendingId !== null;
  const locked = sending || generating || stopping || docBusy || view === "loading";

  /** 답 하나가 끝날 때까지 2초마다 조회한다. 상태는 응답이 온 뒤에만 바꾼다 */
  function follow(sid: string, mid: string) {
    poller.current?.abort();
    const controller = new AbortController();
    poller.current = controller;
    waitForReply(sid, mid, controller.signal).then(
      (reply) => {
        if (controller.signal.aborted) return;
        setMessages((prev) => prev.map((m) => (m.messageId === mid ? reply : m)));
        setPendingId((id) => (id === mid ? null : id));
        onChanged();
      },
      (error: unknown) => {
        if (controller.signal.aborted || isAbort(error)) return;
        setMessages((prev) =>
          prev.map((m) =>
            m.messageId === mid
              ? { ...m, status: "FAILED", error: { code: POLL_FAILED, message: errorText(error), retryable: true } }
              : m,
          ),
        );
        setPendingId((id) => (id === mid ? null : id));
      },
    );
  }

  // 대화를 열면 서버에서 읽고, 만드는 중인 답이 있으면 이어서 기다린다. 막 만든 대화(seed)도 서버 글로 다시 맞춘다
  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    getChatSession(sessionId).then(
      (session) => {
        if (!active) return;
        setMessages(session.messages);
        setTitle(session.title);
        setView("ready");
        const pending = lastPending(session.messages);
        setPendingId(pending?.messageId ?? null);
        if (pending) follow(session.sessionId, pending.messageId);
      },
      (error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 404) {
          setCurrentId(null); // 아래에서 보내면 새 대화를 만든다
          setMessages([]);
          setPendingId(null);
          setView("missing");
        } else if (seed?.pendingId) {
          follow(seed.sessionId, seed.pendingId); // 읽기만 실패했다. 받은 글로 계속 기다린다
        } else {
          setView("error");
        }
      },
    );
    return () => {
      active = false;
    };
    // 대화마다 칸을 새로 만들므로(key) 처음과 다시 읽기를 누를 때만 읽는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, loadAttempt]);

  // 화면을 떠나면 조회를 멈춘다 (서버의 답 만들기는 계속된다)
  useEffect(() => () => poller.current?.abort(), []);

  // 글이 늘면 입력칸이 화면 아래에 오게 내린다
  useEffect(() => {
    if (messages.length > 0) endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  async function send(text: string, attachments?: { documentId: string }[]) {
    const message = text.trim();
    if (!message || locked) return;
    setSending(true);
    setStopError(null);
    setDraft("");
    setResumeOpen(false);
    const user: ChatMessage = {
      messageId: `local-${Date.now()}`,
      role: "USER",
      status: "COMPLETED",
      content: message,
      attachments,
    };
    setMessages((prev) => [...prev, user, { messageId: PENDING_ID, role: "ASSISTANT", status: "PENDING" }]);
    try {
      const started = await sendChat({ sessionId: currentId ?? undefined, message, attachments });
      const sent: ChatMessage = { ...user, messageId: started.userMessageId };
      const pending: ChatMessage = { messageId: started.messageId, role: "ASSISTANT", status: "PENDING" };
      setMessages((prev) =>
        prev.map((m) => (m.messageId === PENDING_ID ? pending : m.messageId === user.messageId ? sent : m)),
      );
      setPendingId(started.messageId);
      follow(started.sessionId, started.messageId);
      if (started.sessionId !== currentId) {
        setCurrentId(started.sessionId);
        onCreated({ sessionId: started.sessionId, messages: [sent, pending], pendingId: started.messageId });
      } else {
        onChanged();
      }
    } catch (error) {
      if (error instanceof ApiError && error.code === "SESSION_NOT_FOUND") setCurrentId(null);
      setMessages((prev) =>
        prev.map((m) =>
          m.messageId === PENDING_ID
            ? {
                messageId: `failed-${Date.now()}`,
                role: "ASSISTANT",
                status: "FAILED",
                error: { code: "CLIENT", message: errorText(error), retryable: true },
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
    }
  }

  /** 멈추기: 조회를 끊고 서버에 알린다. 그사이 답이 끝났으면 그 답을 보여 준다 */
  async function stop() {
    const sid = currentId;
    const mid = pendingId;
    if (!sid || !mid || stopping) return;
    poller.current?.abort();
    setStopping(true);
    setStopError(null);
    try {
      const result = await cancelChatMessage(sid, mid);
      setMessages((prev) => prev.map((m) => (m.messageId === mid ? result : m)));
      if (isSettled(result)) setPendingId(null);
      else follow(sid, mid);
      onChanged();
    } catch {
      setStopError("멈추지 못했어요. 답이 오면 보여 드릴게요.");
      follow(sid, mid);
    } finally {
      setStopping(false);
    }
  }

  /** 실패·멈춘 답 바로 앞의 사용자 말을 다시 보낸다. 조회만 실패했으면 같은 답을 다시 확인한다 */
  function retry(messageId: string) {
    const index = messages.findIndex((m) => m.messageId === messageId);
    if (index < 0) return;
    const target = messages[index];
    if (target.status === "FAILED" && target.error?.code === POLL_FAILED && currentId) {
      setMessages((prev) =>
        prev.map((m) => (m.messageId === messageId ? { ...m, status: "PROCESSING", error: undefined } : m)),
      );
      setPendingId(messageId);
      follow(currentId, messageId);
      return;
    }
    const question = messages
      .slice(0, index)
      .reverse()
      .find((m) => m.role === "USER" && m.content);
    if (question?.content) void send(question.content, question.attachments);
  }

  function onResumeReady(documentId: string) {
    setResumeOpen(false);
    void send("이력서를 올렸어요. 이력서로 맞는 공고와 청년정책 찾아 줘", [{ documentId }]);
  }

  function onPdfReady(documentId: string, fileName: string, kind: "RESUME" | "COVER_LETTER") {
    const what = kind === "COVER_LETTER" ? "자기소개서" : "이력서";
    void send(`${what} ‘${fileName}’을 올렸어요. 내 서류로 맞는 공고와 청년정책 찾아 줘`, [{ documentId }]);
  }

  const last = messages[messages.length - 1];
  const suggestion = last && last.messageId !== hiddenSuggestionFor ? interviewSuggestion(last) : null;
  return (
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex flex-1 flex-col gap-6 pt-6 pb-8">
        {view === "loading" ? (
          <SkeletonGroup label="대화를 불러오는 중" className="flex flex-col gap-4">
            <Skeleton className="h-10 w-2/5 self-end" />
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-1/2" />
          </SkeletonGroup>
        ) : view === "missing" ? (
          <div className="flex flex-col gap-1">
            <h1 className="text-h3 font-bold text-grey-900">대화를 찾지 못했어요</h1>
            <p className="text-body text-grey-700">지웠거나 다른 계정으로 나눈 대화일 수 있어요. 아래에서 새로 물어볼 수 있어요.</p>
          </div>
        ) : view === "error" ? (
          <div role="alert" className="flex flex-col items-start gap-3">
            <p className="text-body text-grey-900">대화를 불러오지 못했어요.</p>
            <Button
              variant="line"
              size="M"
              onClick={() => {
                setView("loading");
                setLoadAttempt((n) => n + 1);
              }}
            >
              다시 불러오기
            </Button>
          </div>
        ) : messages.length === 0 ? (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1">
              <h1 className="text-h2 font-bold text-grey-900">어떤 공고를 찾아 드릴까요?</h1>
              <p className="text-body text-grey-700">
                지역, 연봉, 직무 같은 조건을 말하거나 이력서를 붙이면 채용공고와 청년정책을 함께 찾아 드려요.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {CHAT_EXAMPLES.map((example) => (
                <Chip key={example} onClick={() => void send(example)} disabled={locked}>
                  {example}
                </Chip>
              ))}
            </div>
          </div>
        ) : (
          <>
            {/* 제목은 첫 질문 앞부분이라 화면에는 보이지 않게 둔다 */}
            <h1 className="sr-only">{title ?? "AI 멘토와 나눈 대화"}</h1>
            <ol aria-live="polite" className="flex flex-col gap-5">
              {messages.map((m) => (
                <li key={m.messageId} className="flex flex-col gap-3">
                  {m.role === "USER" ? (
                    <UserBubble message={m} />
                  ) : (
                    <AssistantMessage
                      message={m}
                      latest={m === last}
                      busy={locked}
                      onAsk={(text) => void send(text)}
                      onRetry={() => retry(m.messageId)}
                    />
                  )}
                </li>
              ))}
            </ol>
          </>
        )}
      </div>

      <div className="sticky bottom-0 flex flex-col gap-2 bg-white pt-2 pb-6">
        {stopError && (
          <p role="alert" className="text-small text-red-500">
            {stopError}
          </p>
        )}
        {resumeOpen ? (
          <ResumeForm onReady={onResumeReady} onCancel={() => setResumeOpen(false)} onProcessingChange={setDocBusy} />
        ) : (
          <PdfDropZone disabled={locked} onReady={onPdfReady} onProcessingChange={setDocBusy}>
            <ChatComposer
              value={draft}
              onChange={setDraft}
              onSubmit={() => void send(draft)}
              onStop={() => void stop()}
              generating={generating}
              stopping={stopping}
              disabled={locked}
              suggestion={suggestion}
              onDismissSuggestion={() => last && setHiddenSuggestionFor(last.messageId)}
            />
          </PdfDropZone>
        )}
        {!resumeOpen && (
          <div className="flex flex-wrap items-center gap-2">
            <Chip onClick={() => setResumeOpen(true)} disabled={locked}>
              이력서 붙여넣고 찾기
            </Chip>
          </div>
        )}
      </div>
      <div ref={endRef} />
    </div>
  );
}
