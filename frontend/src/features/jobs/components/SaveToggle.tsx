"use client";

import { Bookmark } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/cn";

/** 공고 저장 아이콘. 화면 안에서만 상태를 바꾼다 (저장 API 연결 전). */
export function SaveToggle({ jobTitle, className }: { jobTitle: string; className?: string }) {
  const [saved, setSaved] = useState(false);
  return (
    <button
      type="button"
      aria-pressed={saved}
      aria-label={`${jobTitle} 저장`}
      onClick={() => setSaved((value) => !value)}
      className={cn("relative z-10 flex size-5 items-center justify-center", className)}
    >
      <Bookmark
        aria-hidden
        className={cn("size-5", saved ? "fill-blue-500 text-blue-500" : "text-grey-400")}
        strokeWidth={2}
      />
    </button>
  );
}
