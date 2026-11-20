"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { loginHref } from "@/features/auth/lib";
import { useUsername } from "@/features/auth/useUsername";
import { ApiError } from "@/lib/api";
import { getChatSession, sendChat, waitForReply } from "../api";
import { asOfLabel, readChatSessionId, saveChatSessionId } from "../lib";
import type { ChatMessage } from "../types";
import { CoverLetterForm, SaveConditions, StartInterview } from "./ChatActions";
import { PolicyCard, PostingCard } from "./ChatCards";
import { ResumeForm } from "./ResumeForm";

const EXAMPLES = [
  "부산 데이터 분석 신입 공고 찾아줘",
  "연봉 3천 이상 부산 공기업 공고 알려줘",
  "내가 받을 수 있는 청년정책 알려줘",
];
const PENDING_ID = "pending";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
}

/**
 * 홈 채팅 (D-39, 개발계획서4 §2). 조건이나 이력서로 채용공고와 청년정책을 함께 찾고, 모의면접 체험으로 이어 준다.
 * 카드·버튼은 서버가 도구 결과로 만든 것만 그린다.
 */
export function ChatPanel() {
  const username = useUsername();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [resumeOpen, setResumeOpen] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const lastQuestion = useRef<{ text: string; attachments?: { documentId: string }[] } | null>(null);

  // 새로 고침 뒤 같은 대화를 다시 그린다 (대화 ID만 탭에 기억)
  useEffect(() => {
    if (!username) return;
    const saved = readChatSessionId();
    if (!saved) return;
    let active = true;
    getChatSession(saved).then(
      (session) => {
        if (!active) return;
        setSessionId(session.sessionId);
        setMessages(session.messages);
      },
      () => active && saveChatSessionId(null),
    );
    return () => {
      active = false;
    };
  }, [username]);

  useEffect(() => () => abort.current?.abort(), []);

  async function send(text: string, attachments?: { documentId: string }[]) {
    const message = text.trim();
    if (!message || busy) return;
    lastQuestion.current = { text: message, attachments };
    setBusy(true);
    setDraft("");
    setMessages((prev) => [
      ...prev.filter((m) => m.messageId !== PENDING_ID),
      { messageId: `local-${Date.now()}`, role: "USER", status: "COMPLETED", content: message, attachments },
      { messageId: PENDING_ID, role: "ASSISTANT", status: "PENDING" },
    ]);
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    try {
      const started = await sendChat({ sessionId: sessionId ?? undefined, message, attachments });
      setSessionId(started.sessionId);
      saveChatSessionId(started.sessionId);
      const reply = await waitForReply(started.sessionId, started.messageId, controller.signal);
      setMessages((prev) => prev.map((m) => (m.messageId === PENDING_ID ? reply : m)));
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (error instanceof ApiError && error.code === "SESSION_NOT_FOUND") {
        setSessionId(null);
        saveChatSessionId(null);
      }
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
      setBusy(false);
    }
  }

  function reset() {
    abort.current?.abort();
    setSessionId(null);
    saveChatSessionId(null);
    setMessages([]);
    setBusy(false);
  }

  function onResumeReady(documentId: string) {
    setResumeOpen(false);
    void send("이력서를 올렸어요. 이력서로 맞는 공고와 청년정책 찾아 줘", [{ documentId }]);
  }

  if (!username) {
    return (
      <section aria-labelledby="chat-title" className="flex min-w-0 flex-1 flex-col gap-3.5">
        <ChatTitle />
        <div className="flex flex-col items-start gap-3 rounded-field border border-grey-200 p-5">
          <p className="text-body text-grey-900">
            로그인하면 채팅으로 조건을 말하거나 이력서를 붙여 부산 채용공고와 청년정책을 함께 찾을 수 있어요.
          </p>
          <Button href={loginHref("/")} size="M">
            로그인
          </Button>
        </div>
      </section>
    );
  }

  const last = messages[messages.length - 1];
  return (
    <section aria-labelledby="chat-title" className="flex min-w-0 flex-1 flex-col gap-3.5">
      <ChatTitle />
      {messages.length > 0 && (
        <ol aria-live="polite" className="flex flex-col gap-5">
          {messages.map((m) => (
            <li key={m.messageId} className="flex flex-col gap-3">
              {m.role === "USER" ? (
                <p className="max-w-[85%] self-end whitespace-pre-wrap rounded-card bg-grey-100 px-3.5 py-2.5 text-body text-grey-900">
                  <span className="sr-only">내 말: </span>
                  {m.content}
                  {m.attachments?.length ? <span className="block text-small text-grey-600">이력서 첨부</span> : null}
                </p>
              ) : (
                <AssistantMessage
                  message={m}
                  latest={m === last}
                  busy={busy}
                  onAsk={(text) => void send(text)}
                  onRetry={() => lastQuestion.current && void send(lastQuestion.current.text, lastQuestion.current.attachments)}
                />
              )}
            </li>
          ))}
        </ol>
      )}

      {resumeOpen ? (
        <ResumeForm onReady={onResumeReady} onCancel={() => setResumeOpen(false)} />
      ) : (
        <AskBox value={draft} onChange={setDraft} onSubmit={() => void send(draft)} disabled={busy} />
      )}
      <div className="flex flex-wrap items-center gap-2">
        {messages.length === 0 && EXAMPLES.map((example) => (
          <Chip key={example} onClick={() => void send(example)} disabled={busy}>
            {example}
          </Chip>
        ))}
        {!resumeOpen && (
          <Chip onClick={() => setResumeOpen(true)} disabled={busy}>
            이력서 붙여넣고 찾기
          </Chip>
        )}
        {messages.length > 0 && (
          <Chip onClick={reset} disabled={busy}>
            새 대화
          </Chip>
        )}
      </div>
      <p className="text-small text-grey-600">
        공고·정책은 공식 데이터(고용24·잡알리오·온통청년)에서 찾고 출처와 기준일을 함께 보여드려요. 적합도는 실제 합격 확률이
        아닙니다.
      </p>
    </section>
  );
}

function ChatTitle() {
  return (
    <h2 id="chat-title" className="text-h3 font-bold text-grey-900">
      AI 멘토와 채팅으로 찾기
    </h2>
  );
}

function AssistantMessage({
  message,
  latest,
  busy,
  onAsk,
  onRetry,
}: {
  message: ChatMessage;
  latest: boolean;
  busy: boolean;
  onAsk: (text: string) => void;
  onRetry: () => void;
}) {
  if (message.status === "PENDING" || message.status === "PROCESSING") {
    return (
      <p role="status" className="text-body text-grey-600">
        AI 멘토가 공고와 정책을 찾고 있어요…
      </p>
    );
  }
  if (message.status === "FAILED") {
    return (
      <div role="alert" className="flex flex-col items-start gap-2">
        <p className="text-body text-grey-900">{message.error?.message ?? "답을 만들지 못했어요."}</p>
        {latest && (message.error?.retryable ?? true) && (
          <Button size="M" variant="line" onClick={onRetry} disabled={busy}>
            다시 보내기
          </Button>
        )}
      </div>
    );
  }
  const postings = (message.cards ?? []).flatMap((c) => (c.type === "POSTING" ? [c.posting] : []));
  const policies = (message.cards ?? []).flatMap((c) => (c.type === "POLICY" ? [c.policy] : []));
  const footnote = [message.notice, asOfLabel(message.dataAsOf)].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col gap-3">
      <p className="text-small font-bold text-grey-600">AI 멘토</p>
      <p className="whitespace-pre-wrap text-body text-grey-900">{message.reply}</p>
      {postings.length > 0 && (
        <section aria-label="찾은 채용공고" className="flex flex-col gap-2">
          <p className="text-small font-bold text-grey-800">채용공고 {postings.length}개</p>
          <ul className="grid gap-2 md:grid-cols-2">
            {postings.map((posting) => (
              <PostingCard key={posting.jobPostingId} posting={posting} />
            ))}
          </ul>
        </section>
      )}
      {policies.length > 0 && (
        <section aria-label="받을 수 있는 청년정책" className="flex flex-col gap-2">
          <p className="text-small font-bold text-grey-800">청년정책 {policies.length}개</p>
          <ul className="grid gap-2 md:grid-cols-2">
            {policies.map((policy) => (
              <PolicyCard key={policy.policyId} policy={policy} />
            ))}
          </ul>
        </section>
      )}
      {footnote && <p className="text-small text-grey-500">{footnote}</p>}
      {(message.actions ?? []).map((action, index) => {
        const key = `${action.type}-${index}`;
        if (action.type === "SAVE_CONDITIONS") return <SaveConditions key={key} action={action} />;
        if (action.type === "START_INTERVIEW") return <StartInterview key={key} action={action} />;
        if (action.type === "REQUEST_COVER_LETTER") return <CoverLetterForm key={key} action={action} />;
        return latest ? (
          <div key={key}>
            <Chip onClick={() => onAsk(`${action.job} 직무로 모의면접 체험해 볼래요`)} disabled={busy}>
              ‘{action.job}’ 모의면접 체험해 보기
            </Chip>
          </div>
        ) : null;
      })}
      {latest && (message.followUps ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.followUps?.map((text) => (
            <Chip key={text} onClick={() => onAsk(text)} disabled={busy}>
              {text}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}

function AskBox({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }
  return (
    <form
      onSubmit={handleSubmit}
      className="flex h-13 w-full items-center gap-3 rounded-field border border-grey-300 pr-1.75 pl-4 focus-within:border-blue-500"
    >
      <label htmlFor="chat-message" className="sr-only">
        AI 멘토에게 보낼 말
      </label>
      <input
        id="chat-message"
        value={value}
        maxLength={1000}
        onChange={(event) => onChange(event.target.value)}
        placeholder="예: 부산에서 연봉 3천 이상, 데이터 분석 신입 공고 찾아줘"
        autoComplete="off"
        className="min-w-0 flex-1 bg-transparent text-body text-grey-900 placeholder:text-grey-500 focus:outline-none"
      />
      <Button type="submit" size="M" disabled={disabled || !value.trim()}>
        보내기
      </Button>
    </form>
  );
}
