import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/cn";

type ArrowLinkProps = {
  href: string;
  children: string;
  tone?: "grey" | "blue";
  className?: string;
};

/** 오른쪽 꺾쇠가 붙은 작은 링크 ("전체 보기", "AI 모의면접으로 연습하기"). */
export function ArrowLink({ href, children, tone = "grey", className }: ArrowLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex items-center gap-0.5 text-small font-medium",
        tone === "grey" ? "text-grey-700 hover:text-grey-900" : "text-blue-500 hover:brightness-90",
        className,
      )}
    >
      {children}
      <ChevronRight aria-hidden className={cn("size-3.5", tone === "grey" && "text-grey-500")} strokeWidth={2} />
    </Link>
  );
}
