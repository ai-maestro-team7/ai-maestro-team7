"use client";

import { PanelLeft, X } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { loginHref } from "@/features/auth/lib";
import { useSessionOwner } from "@/features/auth/useSessionOwner";
import { ApiError } from "@/lib/api";
import { chatHref } from "../lib";
import { useChatSessions } from "../sessions";
import type { ChatSessionSummary } from "../types";
import { ChatSidebar } from "./ChatSidebar";
import { ChatThread, type ThreadSeed } from "./ChatThread";

/**
 * 채팅 Agent 화면 (`/chat/?s={sessionId}`). 왼쪽은 대화 목록(고정·삭제), 오른쪽은 고른 대화와 아래 입력칸이다.
 * `?s=`가 없으면 새 대화다. 좁은 화면에서는 목록을 버튼으로 연다.
 */
export function ChatWorkspace() {
  const owner = useSessionOwner();
  if (!owner) {
    return (
      <div className="flex w-full flex-col items-start gap-3 py-10">
        <h1 className="text-h2 font-bold text-grey-900">AI 멘토와 채팅</h1>
        <p className="text-body text-grey-700">
          로그인하면 조건을 말하거나 이력서를 붙여 부산 채용공고와 청년정책을 함께 찾을 수 있어요. 나눈 대화는 목록에 남아요.
        </p>
        <Button href={loginHref("/chat/")} size="M">
          로그인
        </Button>
      </div>
    );
  }
  // 사용자가 바뀌면(다른 탭에서 계정 변경 포함) 목록과 대화를 통째로 새로 만든다
  return <Workspace key={owner} />;
}

function Workspace() {
  const router = useRouter();
  const sessionId = useSearchParams().get("s");
  const sessions = useChatSessions();
  const [seed, setSeed] = useState<ThreadSeed | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [deleting, setDeleting] = useState<ChatSessionSummary | null>(null);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [listError, setListError] = useState<string | null>(null);

  function handleCreated(next: ThreadSeed) {
    setSeed(next);
    sessions.reload();
    router.replace(chatHref(next.sessionId));
  }

  function handlePin(session: ChatSessionSummary, pinned: boolean) {
    setListError(null);
    sessions.pin(session.sessionId, pinned).catch(() => {
      setListError(pinned ? "고정하지 못했어요. 다시 시도해 주세요." : "고정을 풀지 못했어요. 다시 시도해 주세요.");
    });
  }

  async function confirmDelete(session: ChatSessionSummary) {
    setDeletePending(true);
    setDeleteError(null);
    try {
      await sessions.remove(session.sessionId);
      setDeleting(null);
      if (session.sessionId === sessionId) router.replace(chatHref());
    } catch (error) {
      setDeleteError(error instanceof ApiError ? error.message : "지우지 못했어요. 다시 시도해 주세요.");
    } finally {
      setDeletePending(false);
    }
  }

  const sidebar = (
    <>
      <ChatSidebar
        state={sessions.state}
        activeId={sessionId}
        onPin={handlePin}
        onDelete={(session) => {
          setDeleteError(null);
          setDeleting(session);
        }}
        onNavigate={() => {
          setSeed(null);
          setDrawerOpen(false);
        }}
      />
      {listError && (
        <p role="alert" className="px-2.5 pt-3 text-small text-red-500">
          {listError}
        </p>
      )}
    </>
  );

  return (
    <>
      <aside className="sticky top-0 hidden max-h-dvh w-65 shrink-0 self-start overflow-y-auto py-6 pr-4 lg:block">
        {sidebar}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col lg:border-l lg:border-grey-200 lg:pl-8">
        <div className="flex items-center justify-between gap-2 pt-4 lg:hidden">
          <Button variant="line" size="M" onClick={() => setDrawerOpen(true)} className="gap-1.5">
            <PanelLeft aria-hidden className="size-4" strokeWidth={2} />
            대화 목록
          </Button>
          <Button href={chatHref()} variant="text" size="M">
            새 대화
          </Button>
        </div>
        <ChatThread
          key={sessionId ?? "new"}
          sessionId={sessionId}
          seed={seed && seed.sessionId === sessionId ? seed : null}
          onCreated={handleCreated}
          onChanged={sessions.reload}
        />
      </div>

      {drawerOpen && <Drawer onClose={() => setDrawerOpen(false)}>{sidebar}</Drawer>}

      {deleting && (
        <Dialog
          title="이 대화를 지울까요?"
          onClose={() => setDeleting(null)}
          locked={deletePending}
          actions={
            <>
              <Button variant="line" size="M" onClick={() => setDeleting(null)} disabled={deletePending}>
                취소
              </Button>
              <Button size="M" onClick={() => void confirmDelete(deleting)} disabled={deletePending}>
                {deletePending ? "지우는 중" : "대화 지우기"}
              </Button>
            </>
          }
        >
          <p className="break-words">{deleting.title}</p>
          <p>지운 대화는 되돌릴 수 없어요.</p>
          {deleteError && (
            <p role="alert" className="text-small text-red-500">
              {deleteError}
            </p>
          )}
        </Dialog>
      )}
    </>
  );
}

/** 좁은 화면의 대화 목록. 브라우저 `<dialog>`라 열려 있는 동안 뒤 화면은 누를 수 없고 Esc로 닫힌다 */
function Drawer({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    dialog.showModal();
    return () => dialog.close();
  }, []);

  return (
    <dialog
      ref={ref}
      aria-label="대화 목록"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className="m-0 h-dvh max-h-none w-72 max-w-[85vw] bg-white backdrop:bg-dark/40"
    >
      <div className="flex min-h-full flex-col gap-3 px-4 py-5">
        <button
          type="button"
          onClick={onClose}
          aria-label="대화 목록 닫기"
          className="flex size-8 items-center justify-center self-end rounded-control text-grey-600 hover:bg-grey-100"
        >
          <X aria-hidden className="size-4.5" strokeWidth={2} />
        </button>
        {children}
      </div>
    </dialog>
  );
}
