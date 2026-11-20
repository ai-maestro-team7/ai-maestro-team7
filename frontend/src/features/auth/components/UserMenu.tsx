"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import { StatusDot } from "@/components/ui/StatusDot";
import { mentorChatHref } from "@/features/mentor/lib";
import { cn } from "@/lib/cn";
import { useDevMode } from "../devMode";
import { ResetDataDialog } from "./ResetDataDialog";

const itemClass = "flex h-10 w-full items-center px-3.5 text-left text-small text-grey-800 hover:bg-grey-50";

/**
 * 오른쪽 위 사용자 메뉴. 이름을 누르면 기본 정보 수정, 저장한 공고, AI 멘토 대화, 로그아웃이 열린다.
 * 바깥을 누르거나 Esc를 누르면 닫힌다.
 * 개발 모드로 로그인했으면 이름 앞에 "개발 모드"가 보이고 메뉴에 "유저 정보 모두 초기화"가 생긴다.
 */
export function UserMenu({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const devMode = useDevMode();
  const root = useRef<HTMLDivElement | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const menuId = useId();

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
    <div ref={root} className="relative flex items-center gap-3">
      {devMode && <StatusDot tone="orange" label="개발 모드" />}
      <button
        ref={trigger}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1 font-medium text-grey-900"
      >
        {username} 님
        <ChevronDown aria-hidden className={cn("size-4 text-grey-500 transition-transform", open && "rotate-180")} strokeWidth={2} />
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          className="absolute top-full right-0 z-20 mt-2 w-40 overflow-hidden rounded-control border border-grey-200 bg-white py-1 shadow-[0_4px_12px_rgba(0,0,0,0.06)]"
        >
          <Link role="menuitem" href="/profile/" className={itemClass} onClick={() => setOpen(false)}>
            기본 정보 수정
          </Link>
          <Link role="menuitem" href="/saved/" className={itemClass} onClick={() => setOpen(false)}>
            저장한 공고
          </Link>
          <Link role="menuitem" href={mentorChatHref()} className={itemClass} onClick={() => setOpen(false)}>
            AI 멘토 대화
          </Link>
          <hr className="my-1 border-grey-200" />
          {devMode && (
            <>
              <button
                type="button"
                role="menuitem"
                className={itemClass}
                onClick={() => {
                  // 확인 창을 닫으면 초점이 메뉴 버튼으로 돌아오게 먼저 옮겨 둔다
                  trigger.current?.focus();
                  setOpen(false);
                  setResetting(true);
                }}
              >
                유저 정보 모두 초기화
              </button>
              <hr className="my-1 border-grey-200" />
            </>
          )}
          <button
            type="button"
            role="menuitem"
            className={cn(itemClass, "text-grey-600")}
            onClick={() => {
              setOpen(false);
              onLogout();
            }}
          >
            로그아웃
          </button>
        </div>
      )}
      {resetting && <ResetDataDialog onClose={() => setResetting(false)} />}
    </div>
  );
}
