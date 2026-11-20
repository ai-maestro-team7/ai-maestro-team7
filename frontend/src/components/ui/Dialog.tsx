"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";

type DialogProps = {
  title: string;
  /** Esc를 누르거나 바깥을 눌렀을 때 */
  onClose: () => void;
  /** 요청을 보내는 동안처럼 닫으면 안 될 때 true */
  locked?: boolean;
  children: ReactNode;
  /** 아래 버튼들 (Button M). 처음 초점이 가는 첫 버튼에는 취소처럼 되돌릴 수 있는 동작을 둔다 */
  actions: ReactNode;
};

/**
 * 확인 창. 화면에 넣으면 바로 열리고, 빼면 닫히면서 열기 전에 초점이 있던 곳으로 돌아간다.
 * 브라우저의 `<dialog>`를 써서 열려 있는 동안 뒤 화면은 누르거나 초점을 옮길 수 없다.
 */
export function Dialog({ title, onClose, locked = false, children, actions }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const opener = document.activeElement;
    dialog.showModal();
    return () => {
      dialog.close();
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, []);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      // Esc: 브라우저가 닫게 두지 않고 화면 상태로 닫는다
      onCancel={(event) => {
        event.preventDefault();
        if (!locked) onClose();
      }}
      // 브라우저가 직접 닫은 경우 (Esc를 연달아 누르면 onCancel을 건너뛴다). 잠겨 있으면 다시 연다
      onClose={(event) => {
        if (event.currentTarget.open) return;
        if (locked) event.currentTarget.showModal();
        else onClose();
      }}
      // 안쪽 여백은 아래 div에 있어서, dialog 자체가 눌렸다면 바깥(배경)을 누른 것이다
      onClick={(event) => {
        if (event.target === event.currentTarget && !locked) onClose();
      }}
      className="m-auto w-[calc(100%-2.5rem)] max-w-100 rounded-card border border-grey-200 bg-white text-grey-900 backdrop:bg-dark/40"
    >
      <div className="flex flex-col gap-5 p-6">
        <h2 id={titleId} className="text-h3 font-bold text-grey-900">
          {title}
        </h2>
        <div className="flex flex-col gap-3 text-body text-grey-700">{children}</div>
        <div className="flex flex-wrap justify-end gap-2">{actions}</div>
      </div>
    </dialog>
  );
}
