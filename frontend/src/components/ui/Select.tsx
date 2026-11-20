"use client";

import { Check, ChevronDown } from "lucide-react";
import { type KeyboardEvent, useEffect, useId, useRef, useState } from "react";
import { cn } from "@/lib/cn";

export type SelectOption = { value: string; label: string };

/**
 * 고르기 칸. 브라우저 기본 목록(기기마다 모양이 다르고 macOS에서는 검은 팝업)이 서비스와 어울리지 않아 목록을 직접 그린다.
 * 모양은 TextField와 같은 칸 + 사용자 메뉴와 같은 흰 목록. WAI-ARIA "select-only combobox" 방식:
 * 칸에 초점이 있고(`aria-activedescendant`) 목록은 `listbox`/`option`이다.
 *
 * 키보드: 열기 Enter·Space·↑↓ · 이동 ↑↓·Home·End·글자 입력 · 고르기 Enter·Space · 닫기 Esc·Tab
 * 꼭 골라야 하는 칸(`required`)이면 안내 문구(placeholder)를 목록에 넣지 않는다. 아니면 맨 위에 "선택 안 함"으로 둔다.
 */
export function Select({
  id,
  value,
  onChange,
  options,
  placeholder,
  required = false,
  invalid = false,
  describedBy,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: ReadonlyArray<SelectOption>;
  placeholder: string;
  required?: boolean;
  invalid?: boolean;
  describedBy?: string;
}) {
  const listId = useId();
  const root = useRef<HTMLDivElement | null>(null);
  const list = useRef<HTMLUListElement | null>(null);
  const typed = useRef({ text: "", at: 0 });
  const items: ReadonlyArray<SelectOption> = required ? options : [{ value: "", label: "선택 안 함" }, ...options];
  const selectedIndex = items.findIndex((item) => item.value === value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(Math.max(selectedIndex, 0));
  const current = options.find((option) => option.value === value);

  // 바깥을 누르면 닫는다
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    return () => document.removeEventListener("pointerdown", onPointer);
  }, [open]);

  // 열린 동안 지금 칸이 보이게 목록을 굴린다 (출생 연도처럼 긴 목록)
  useEffect(() => {
    if (!open) return;
    list.current?.querySelector<HTMLElement>(`[data-index="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  function openList() {
    setActive(Math.max(selectedIndex, 0));
    setOpen(true);
  }

  function choose(index: number) {
    const item = items[index];
    if (item) onChange(item.value);
    setOpen(false);
  }

  /** 글자를 치면 그 글자로 시작하는 칸으로 간다. 1초 안에 이어 치면 이어 친 말로 찾는다 */
  function typeAhead(key: string) {
    const now = Date.now();
    typed.current = { text: now - typed.current.at < 1000 ? typed.current.text + key : key, at: now };
    const text = typed.current.text.toLowerCase();
    const start = open ? active + 1 : 0;
    const order = [...items.keys()].map((i) => (start + i) % items.length);
    const found = order.find((i) => items[i].label.toLowerCase().startsWith(text));
    if (found === undefined) return;
    if (open) setActive(found);
    else onChange(items[found].value);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const last = items.length - 1;
    if (!open) {
      if (["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) {
        event.preventDefault();
        openList();
      } else if (event.key.length === 1 && !event.metaKey && !event.ctrlKey) {
        typeAhead(event.key);
      }
      return;
    }
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((i) => Math.min(i + 1, last));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((i) => Math.max(i - 1, 0));
        break;
      case "Home":
        event.preventDefault();
        setActive(0);
        break;
      case "End":
        event.preventDefault();
        setActive(last);
        break;
      case "Enter":
      case " ":
        event.preventDefault();
        choose(active);
        break;
      case "Escape":
        event.preventDefault();
        setOpen(false);
        break;
      case "Tab":
        setOpen(false);
        break;
      default:
        if (event.key.length === 1 && !event.metaKey && !event.ctrlKey) typeAhead(event.key);
    }
  }

  const optionId = (index: number) => `${listId}-option-${index}`;

  return (
    <div ref={root} className="relative w-full">
      <button
        id={id}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open ? optionId(active) : undefined}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
        className={cn(
          "flex h-12 w-full cursor-pointer items-center rounded-field border bg-white pr-11 pl-3.75 text-left text-body transition-colors hover:border-grey-400 focus:outline-none",
          current ? "text-grey-900" : "text-grey-500",
          invalid ? "border-red-500 hover:border-red-500" : open ? "border-blue-500" : "border-grey-300",
          "focus-visible:border-blue-500",
        )}
      >
        <span className="truncate">{current ? current.label : placeholder}</span>
      </button>
      <ChevronDown
        aria-hidden
        className={cn(
          "pointer-events-none absolute top-1/2 right-3.75 size-5 -translate-y-1/2 text-grey-500 transition-transform",
          open && "rotate-180",
        )}
        strokeWidth={2}
      />
      <ul
        ref={list}
        id={listId}
        role="listbox"
        aria-labelledby={id}
        tabIndex={-1}
        hidden={!open}
        className="absolute top-full right-0 left-0 z-30 mt-1.5 max-h-64 overflow-y-auto rounded-field border border-grey-200 bg-white py-1 shadow-[0_4px_12px_rgba(0,0,0,0.06)]"
      >
        {items.map((item, index) => {
          const selected = item.value === value;
          return (
            <li
              key={item.value || "__none"}
              id={optionId(index)}
              data-index={index}
              role="option"
              aria-selected={selected}
              // 누르는 동안 칸의 초점을 잃지 않게 한다 (키보드 사용자와 같은 흐름)
              onPointerDown={(event) => event.preventDefault()}
              onPointerEnter={() => setActive(index)}
              onClick={() => choose(index)}
              className={cn(
                "flex h-10 cursor-pointer items-center justify-between gap-2 px-3.75 text-body",
                index === active && "bg-grey-50",
                selected ? "font-medium text-blue-500" : item.value ? "text-grey-800" : "text-grey-500",
              )}
            >
              <span className="truncate">{item.label}</span>
              {selected && <Check aria-hidden className="size-4.5 shrink-0" strokeWidth={2.25} />}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
