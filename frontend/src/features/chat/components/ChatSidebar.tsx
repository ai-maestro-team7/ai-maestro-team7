"use client";

import { Ellipsis, Pin } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Skeleton, SkeletonGroup } from "@/components/ui/Skeleton";
import { cn } from "@/lib/cn";
import { chatHref } from "../lib";
import type { SessionsState } from "../sessions";
import type { ChatSessionSummary } from "../types";

const itemClass = "flex h-9 w-full items-center px-3 text-left text-small text-grey-800 hover:bg-grey-50";

/**
 * 채팅 화면 왼쪽 대화 목록. 새 대화, 고정한 대화, 최근 대화 순서다.
 * 대화마다 `…` 메뉴에서 고정·고정 해제와 삭제를 고른다. 링크를 누르면 `onNavigate`를 부른다 (좁은 화면에서 목록 닫기).
 */
export function ChatSidebar({
  state,
  activeId,
  onPin,
  onDelete,
  onNavigate,
}: {
  state: SessionsState;
  activeId: string | null;
  onPin: (session: ChatSessionSummary, pinned: boolean) => void;
  onDelete: (session: ChatSessionSummary) => void;
  onNavigate?: () => void;
}) {
  return (
    <nav
      aria-label="대화 목록"
      className="flex w-full flex-col gap-5"
      onClick={(event) => {
        if ((event.target as HTMLElement).closest("a")) onNavigate?.();
      }}
    >
      <Button href={chatHref()} variant="line" size="M" fullWidth>
        새 대화
      </Button>
      {state.status === "loading" ? (
        <SkeletonGroup label="대화 목록을 불러오는 중" className="flex flex-col gap-2.5 px-2.5">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-4/5" />
        </SkeletonGroup>
      ) : state.status === "error" ? (
        <p className="px-2.5 text-small text-grey-600">{state.message}</p>
      ) : state.sessions.length === 0 ? (
        <p className="px-2.5 text-small text-grey-500">아직 나눈 대화가 없어요.</p>
      ) : (
        <>
          <SessionGroup
            title="고정됨"
            sessions={state.sessions.filter((s) => s.pinned)}
            activeId={activeId}
            onPin={onPin}
            onDelete={onDelete}
          />
          <SessionGroup
            title="최근 대화"
            sessions={state.sessions.filter((s) => !s.pinned)}
            activeId={activeId}
            onPin={onPin}
            onDelete={onDelete}
          />
        </>
      )}
    </nav>
  );
}

function SessionGroup({
  title,
  sessions,
  activeId,
  onPin,
  onDelete,
}: {
  title: string;
  sessions: ChatSessionSummary[];
  activeId: string | null;
  onPin: (session: ChatSessionSummary, pinned: boolean) => void;
  onDelete: (session: ChatSessionSummary) => void;
}) {
  const headingId = useId();
  if (sessions.length === 0) return null;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-1.5">
      <h2 id={headingId} className="px-2.5 text-small font-medium text-grey-600">
        {title}
      </h2>
      <ul className="flex flex-col gap-0.5">
        {sessions.map((session) => (
          <SessionItem
            key={session.sessionId}
            session={session}
            current={session.sessionId === activeId}
            onPin={onPin}
            onDelete={onDelete}
          />
        ))}
      </ul>
    </section>
  );
}

function SessionItem({
  session,
  current,
  onPin,
  onDelete,
}: {
  session: ChatSessionSummary;
  current: boolean;
  onPin: (session: ChatSessionSummary, pinned: boolean) => void;
  onDelete: (session: ChatSessionSummary) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLLIElement>(null);
  const menuId = useId();

  // 바깥을 누르거나 Esc를 누르면 메뉴를 닫는다
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <li ref={root} className="group relative">
      <Link
        href={chatHref(session.sessionId)}
        aria-current={current ? "page" : undefined}
        className={cn(
          "flex items-center gap-1.5 rounded-control py-2 pr-9 pl-2.5 text-small",
          current ? "bg-grey-100 font-medium text-grey-900" : "text-grey-800 hover:bg-grey-50",
        )}
      >
        {session.pinned && <Pin aria-hidden className="size-3.5 shrink-0 text-grey-500" strokeWidth={2} />}
        <span className="truncate">{session.title}</span>
        {session.pendingMessageId && (
          <span className="ml-auto size-1.5 shrink-0 rounded-full bg-blue-500">
            <span className="sr-only">(답을 만드는 중)</span>
          </span>
        )}
      </Link>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`${session.title} 대화 메뉴`}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "absolute top-1/2 right-1 flex size-7 -translate-y-1/2 items-center justify-center rounded-control text-grey-500",
          "hover:bg-grey-200 hover:text-grey-800 focus-visible:opacity-100",
          // 마우스로는 올렸을 때만, 터치 화면에서는 늘 보인다
          open || current ? "opacity-100" : "opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100",
        )}
      >
        <Ellipsis aria-hidden className="size-4" strokeWidth={2} />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute top-full right-0 z-20 mt-1 w-32 overflow-hidden rounded-control border border-grey-200 bg-white py-1 shadow-[0_4px_12px_rgba(0,0,0,0.06)]"
        >
          <button
            type="button"
            role="menuitem"
            className={itemClass}
            onClick={() => {
              setOpen(false);
              onPin(session, !session.pinned);
            }}
          >
            {session.pinned ? "고정 해제" : "고정"}
          </button>
          <button
            type="button"
            role="menuitem"
            className={cn(itemClass, "text-red-500")}
            onClick={() => {
              setOpen(false);
              onDelete(session);
            }}
          >
            삭제
          </button>
        </div>
      )}
    </li>
  );
}
