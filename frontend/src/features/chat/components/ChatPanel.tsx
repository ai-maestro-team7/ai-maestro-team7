"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { loginHref } from "@/features/auth/lib";
import { useSessionOwner } from "@/features/auth/useSessionOwner";
import { ApiError } from "@/lib/api";
import { sendChat } from "../api";
import { CHAT_EXAMPLES, chatHref } from "../lib";
import { AttachButton, PdfDropZone } from "./PdfAttach";
import { ResumeForm } from "./ResumeForm";

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
}

/**
 * 홈 채팅창 (D-39, 개발계획서4 §2). 말을 보내거나 예시·서류를 고르면 첫 턴을 시작하고 채팅 화면(`/chat/`)으로 넘어간다.
 * 답은 채팅 화면이 기다린다. 대화는 채팅 화면 왼쪽 목록에 남는다.
 */
export function ChatPanel() {
  const owner = useSessionOwner();
  if (!owner) {
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
  // 사용자가 바뀌면(다른 탭에서 계정 변경 포함) 입력 상태를 새로 만든다
  return <Launcher key={owner} />;
}

function Launcher() {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resumeOpen, setResumeOpen] = useState(false);
  // 서류를 올려 글자·역량을 찾는 중. 이때 보내면 끝난 서류가 대화에 붙지 못하므로 보내기를 막는다
  const [docBusy, setDocBusy] = useState(false);
  const locked = starting || docBusy;

  async function start(text: string, attachments?: { documentId: string }[]) {
    const message = text.trim();
    if (!message || locked) return;
    setStarting(true);
    setError(null);
    try {
      const started = await sendChat({ message, attachments });
      router.push(chatHref(started.sessionId)); // 넘어가는 동안 다시 보내지 않게 잠근 채로 둔다
    } catch (e) {
      setError(errorText(e));
      setStarting(false);
    }
  }

  function onResumeReady(documentId: string) {
    setResumeOpen(false);
    void start("이력서를 올렸어요. 이력서로 맞는 공고와 청년정책 찾아 줘", [{ documentId }]);
  }

  function onPdfReady(documentId: string, fileName: string, kind: "RESUME" | "COVER_LETTER") {
    const what = kind === "COVER_LETTER" ? "자기소개서" : "이력서";
    void start(`${what} ‘${fileName}’을 올렸어요. 내 서류로 맞는 공고와 청년정책 찾아 줘`, [{ documentId }]);
  }

  return (
    <section aria-labelledby="chat-title" className="flex min-w-0 flex-1 flex-col gap-3.5">
      <div className="flex items-center justify-between gap-3">
        <ChatTitle />
        <Link href={chatHref()} className="text-small font-medium text-grey-700 hover:text-grey-900">
          지난 대화
        </Link>
      </div>

      {resumeOpen ? (
        <ResumeForm onReady={onResumeReady} onCancel={() => setResumeOpen(false)} onProcessingChange={setDocBusy} />
      ) : (
        <PdfDropZone disabled={locked} onReady={onPdfReady} onProcessingChange={setDocBusy}>
          <AskBox value={draft} onChange={setDraft} onSubmit={() => void start(draft)} disabled={locked} starting={starting} />
        </PdfDropZone>
      )}
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {CHAT_EXAMPLES.map((example) => (
          <Chip key={example} onClick={() => void start(example)} disabled={locked}>
            {example}
          </Chip>
        ))}
        {!resumeOpen && (
          <Chip onClick={() => setResumeOpen(true)} disabled={locked}>
            이력서 붙여넣고 찾기
          </Chip>
        )}
      </div>
      <p className="text-small text-grey-600">
        공고·정책은 공식 데이터(고용24·잡알리오·온통청년)에서 먼저 찾고, 없으면 팀이 넣어 둔 데이터에서 찾아 따로 표시해요.
        이력서·자기소개서 PDF는 클립 버튼으로 고르거나 입력칸에 끌어다 놓을 수 있어요 (10MB 이하). 적합도는 실제 합격 확률이
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

function AskBox({
  value,
  onChange,
  onSubmit,
  disabled,
  starting,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  starting: boolean;
}) {
  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }
  return (
    <form
      onSubmit={handleSubmit}
      className="flex h-13 w-full items-center gap-2 rounded-field border border-grey-300 pr-1.75 pl-1.75 focus-within:border-blue-500"
    >
      <AttachButton disabled={disabled} />
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
        {starting ? "여는 중" : "보내기"}
      </Button>
    </form>
  );
}
