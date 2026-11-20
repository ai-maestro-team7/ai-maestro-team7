"use client";

import { Bookmark } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
import { loginHref } from "@/features/auth/lib";
import { useUsername } from "@/features/auth/useUsername";
import { cn } from "@/lib/cn";
import { saveJob, unsaveJob, useSavedIds } from "../saved";

/**
 * 공고 저장 아이콘. 누르면 관심 공고로 저장하고(`POST /api/v1/opportunities/saved`), 저장된 공고를 다시 누르면
 * 저장을 푼다(`DELETE /saved/{id}`, "저장한 공고" 화면의 "관심 해제"와 같다). 저장한 공고는 오른쪽 위 "저장한 공고"에서 본다.
 */
export function SaveToggle({ jobPostingId, jobTitle, className }: { jobPostingId: string; jobTitle: string; className?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const username = useUsername();
  const saved = useSavedIds().has(jobPostingId);
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleClick() {
    if (pending) return;
    if (!username) {
      router.push(loginHref(pathname));
      return;
    }
    setPending(true);
    setFailed(false);
    try {
      await (saved ? unsaveJob(jobPostingId) : saveJob(jobPostingId));
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
      aria-label={`${jobTitle} 저장`} /* 토글 버튼이라 이름은 그대로 두고, 저장 여부는 aria-pressed로 알린다 */
      title={
        failed
          ? saved
            ? "저장을 풀지 못했어요. 다시 눌러 주세요."
            : "저장하지 못했어요. 다시 눌러 주세요."
          : saved
            ? "저장한 공고 (누르면 저장 해제)"
            : "저장"
      }
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
