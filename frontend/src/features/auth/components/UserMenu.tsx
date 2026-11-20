"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { type PointerEvent as ReactPointerEvent, useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";

const itemClass = "flex h-10 w-full items-center px-3.5 text-left text-small text-grey-800 hover:bg-grey-50";

/** 마우스가 메뉴 밖으로 나간 뒤 닫힐 때까지 기다리는 시간. 대각선으로 움직이다 잠깐 벗어나도 닫히지 않게 한다. */
const CLOSE_DELAY_MS = 150;

/**
 * 오른쪽 위 사용자 메뉴. 마우스를 올리면 기본 정보 수정, 저장한 공고, 로그아웃이 아래로 펼쳐진다.
 * 터치와 키보드는 이름을 눌러서 열고 닫는다. 바깥을 누르거나 Esc를 누르면 닫힌다.
 */
export function UserMenu({ username, onLogout }: { username: string; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastPointer = useRef<string>("");
  const menuId = useId();

  const cancelClose = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    closeTimer.current = null;
  };
  const close = () => {
    cancelClose();
    setOpen(false);
  };

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

  useEffect(() => cancelClose, []);

  // 터치는 pointerenter 뒤에 click이 바로 따라와서, 마우스일 때만 올리기로 연다
  const onPointerEnter = (event: ReactPointerEvent) => {
    if (event.pointerType !== "mouse") return;
    cancelClose();
    setOpen(true);
  };
  const onPointerLeave = (event: ReactPointerEvent) => {
    if (event.pointerType !== "mouse") return;
    cancelClose();
    closeTimer.current = setTimeout(() => setOpen(false), CLOSE_DELAY_MS);
  };

  return (
    <div ref={root} className="relative" onPointerEnter={onPointerEnter} onPointerLeave={onPointerLeave}>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onPointerDown={(event) => {
          lastPointer.current = event.pointerType;
        }}
        onClick={() => {
          // 마우스는 올리는 순간 이미 열려 있으니 눌러도 닫지 않는다. 터치·키보드는 눌러서 열고 닫는다
          if (lastPointer.current === "mouse") setOpen(true);
          else setOpen((value) => !value);
          lastPointer.current = "";
        }}
        className="flex items-center gap-1 font-medium text-grey-900"
      >
        {username} 님
        <ChevronDown aria-hidden className={cn("size-4 text-grey-500 transition-transform", open && "rotate-180")} strokeWidth={2} />
      </button>
      {/* 바깥 틀의 pt-2가 이름과 메뉴 사이 틈을 메워, 마우스가 그 틈을 지나도 메뉴 밖으로 나간 것이 되지 않는다.
          닫혀 있을 때는 invisible이라 화면 읽기 프로그램과 Tab 순서에서도 빠진다 */}
      <div
        className={cn(
          "absolute top-full right-0 z-20 w-40 pt-2 transition-[opacity,translate,visibility] duration-150 ease-out motion-reduce:transition-none",
          open ? "visible translate-y-0 opacity-100" : "invisible -translate-y-1 opacity-0",
        )}
      >
        <div
          id={menuId}
          role="menu"
          className="overflow-hidden rounded-control border border-grey-200 bg-white py-1 shadow-[0_4px_12px_rgba(0,0,0,0.06)]"
        >
          <Link role="menuitem" href="/profile/" className={itemClass} onClick={close}>
            기본 정보 수정
          </Link>
          <Link role="menuitem" href="/saved/" className={itemClass} onClick={close}>
            저장한 공고
          </Link>
          <hr className="my-1 border-grey-200" />
          <button
            type="button"
            role="menuitem"
            className={cn(itemClass, "text-grey-600")}
            onClick={() => {
              close();
              onLogout();
            }}
          >
            로그아웃
          </button>
        </div>
      </div>
    </div>
  );
}
