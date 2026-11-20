import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/**
 * 본문 영역 (폭 1080px, 위 40px · 아래 96px 여백). `gap`은 화면마다 Figma 값이 달라 넘겨받는다.
 */
export function PageContainer({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <main
      id="main"
      className={cn("mx-auto flex w-full max-w-content flex-1 flex-col px-5 pt-10 pb-24 xl:px-0", className)}
    >
      {children}
    </main>
  );
}

/**
 * 본문 700px + 오른쪽 332px, 사이 48px. `lg` 미만에서는 위아래로 쌓는다.
 * stickyRail이면 넓은 화면에서 오른쪽 칸이 스크롤을 따라 위에 붙어 있다 (공고 상세의 적합도·버튼).
 */
export function TwoColumn({
  main,
  rail,
  className,
  stickyRail = false,
}: {
  main: ReactNode;
  rail: ReactNode;
  className?: string;
  stickyRail?: boolean;
}) {
  return (
    <div className={cn("flex w-full flex-col gap-12 lg:flex-row lg:items-start", className)}>
      <div className="flex w-full min-w-0 flex-col lg:max-w-main lg:flex-1">{main}</div>
      <div className={cn("flex w-full flex-col lg:w-rail lg:shrink-0", stickyRail && "lg:sticky lg:top-6")}>{rail}</div>
    </div>
  );
}
