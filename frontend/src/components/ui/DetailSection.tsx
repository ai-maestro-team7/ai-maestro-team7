import type { ReactNode } from "react";

/** 상세 화면 본문 구역: 위 1px grey-200 선 + H3 제목 + 내용. */
export function DetailSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex w-full flex-col gap-3 border-t border-grey-200 pt-6 pb-6">
      <h2 className="text-h3 font-bold text-grey-900">{title}</h2>
      {children}
    </section>
  );
}

/** 가운뎃점(·) 목록 */
export function DotList({ items }: { items: string[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {items.map((item) => (
        <li key={item} className="flex gap-2.5 text-body text-grey-800">
          <span aria-hidden className="text-grey-500">
            ·
          </span>
          {item}
        </li>
      ))}
    </ul>
  );
}

/** 오른쪽 상자의 "라벨 + 값" 묶음 */
export function LabeledValue({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="text-small text-grey-600">{label}</p>
      <div className="text-body text-grey-900">{children}</div>
    </div>
  );
}
