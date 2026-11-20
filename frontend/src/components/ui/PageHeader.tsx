import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  /** 제목 줄 오른쪽 요소 (예: 모의면접 Steps) */
  aside?: ReactNode;
};

/** 화면 제목 (Title 26px) + 설명 (Body, grey-700). */
export function PageHeader({ title, description, aside }: PageHeaderProps) {
  return (
    <header className="flex w-full flex-col gap-2">
      <div className="flex w-full flex-wrap items-center justify-between gap-x-6 gap-y-3">
        <h1 className="text-title font-bold text-grey-900">{title}</h1>
        {aside}
      </div>
      {description && <p className="text-body text-grey-700">{description}</p>}
    </header>
  );
}
