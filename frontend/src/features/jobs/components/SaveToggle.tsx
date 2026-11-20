"use client";

import { Bookmark } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { loginHref } from "@/features/auth/lib";
import { useUsername } from "@/features/auth/useUsername";
import { cn } from "@/lib/cn";
import { saveJob, useSavedIds } from "../saved";

/**
 * 공고 저장 아이콘. 누르면 관심 공고로 저장한다 (`POST /api/v1/opportunities/saved`).
 * 저장한 공고는 오른쪽 위 "저장한 공고"에서 볼 수 있다. 저장은 그 화면의 "관심 해제"로 풀고, 여기서 다시 눌러도 그대로다.
 */
export function SaveToggle({ jobPostingId, jobTitle, className }: { jobPostingId: string; jobTitle: string; className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const username = useUsername();
  const saved = useSavedIds().has(jobPostingId);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleClick() {
    if (saved || pending) return;
    if (!username) {
      router.push(loginHref(pathname));
      return;
    }
    setPending(true);
    setFailed(false);
    try {
      await saveJob(jobPostingId);
    } catch {
      setFailed(true);
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      aria-pressed={saved}
      aria-label={saved ? `${jobTitle} 저장됨` : `${jobTitle} 저장`}
      title={failed ? "저장하지 못했어요. 다시 눌러 주세요." : saved ? "저장한 공고" : "저장"}
      onClick={() => void handleClick()}
      className={cn("relative z-10 flex size-5 items-center justify-center", pending && "opacity-50", className)}
    >
      <Bookmark
        aria-hidden
        className={cn("size-5", saved ? "fill-blue-500 text-blue-500" : failed ? "text-red-500" : "text-grey-400")}
        strokeWidth={2}
      />
    </button>
  );
}
