"use client";

import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiErrorNotice, ApiLoading } from "@/features/auth/components/ApiFallback";
import { useApi } from "@/lib/useApi";
import { getSavedJobs, unsaveJob } from "../saved";

/** `2026-11-21T10:12:00+09:00` → `11.21` */
function shortDate(value: string | undefined): string {
  const match = value?.match(/^\d{4}-(\d{2})-(\d{2})/);
  return match ? `${match[1]}.${match[2]}` : "";
}

/** 저장한 공고 목록 (`GET /api/v1/opportunities/saved`). 최근에 저장한 것이 위에 온다. */
export function SavedList() {
  const [saved, reload] = useApi("saved-jobs", getSavedJobs);
  // 관심 해제한 공고는 목록을 다시 부르지 않고 바로 뺀다
  const [removed, setRemoved] = useState<ReadonlySet<string>>(() => new Set());
  const [pending, setPending] = useState<string>();
  const [failed, setFailed] = useState<string>();

  async function handleUnsave(jobPostingId: string) {
    if (pending) return;
    setPending(jobPostingId);
    setFailed(undefined);
    try {
      await unsaveJob(jobPostingId);
      setRemoved((prev) => new Set(prev).add(jobPostingId));
    } catch {
      setFailed(jobPostingId);
    } finally {
      setPending(undefined);
    }
  }

  if (saved.status === "loading") return <ApiLoading />;
  if (saved.status === "error") return <ApiErrorNotice error={saved.error} onRetry={reload} />;

  const items = saved.data.items
    .filter((item) => !removed.has(item.jobPostingId))
    .sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  if (items.length === 0) {
    return (
      <div className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
        <p className="text-body font-bold text-grey-900">아직 저장한 공고가 없어요</p>
        <p className="text-small text-grey-600">채용 공고에서 책갈피 아이콘을 누르면 여기에 모여요.</p>
        <Button href="/jobs" size="M">
          채용 공고 보기
        </Button>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-3">
      <p className="text-small text-grey-600">
        <span className="font-bold text-grey-900">{items.length}건</span>
      </p>
      <ul className="flex flex-col border-t border-grey-800">
        {items.map((item) => (
          <li key={item.jobPostingId} className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-grey-200 py-4">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <Link
                href={`/jobs/detail/?id=${encodeURIComponent(item.jobPostingId)}`}
                className="truncate text-body font-bold text-grey-900 hover:text-blue-500"
              >
                {item.title ?? "공고 보기"}
              </Link>
              <p className="truncate text-small text-grey-600">
                {[item.organization, item.isBusan ? "부산" : null].filter(Boolean).join(" · ")}
              </p>
            </div>
            <dl className="flex shrink-0 gap-5 text-small text-grey-600">
              {/* 관심 공고는 따로 표시하지 않고, 지원 목표로 담은 공고만 표시한다 */}
              {item.kind === "TARGET" && (
                <div>
                  <dt className="sr-only">구분</dt>
                  <dd className="font-medium text-grey-900">지원 목표</dd>
                </div>
              )}
              {item.closesAt && (
                <div>
                  <dt className="inline">마감 </dt>
                  <dd className="inline font-medium text-grey-900">{shortDate(item.closesAt)}</dd>
                </div>
              )}
              <div>
                <dt className="inline">저장 </dt>
                <dd className="inline">{shortDate(item.savedAt)}</dd>
              </div>
            </dl>
            <Button
              variant="line"
              size="M"
              disabled={pending === item.jobPostingId}
              aria-label={`${item.title ?? "공고"} 관심 해제`}
              onClick={() => void handleUnsave(item.jobPostingId)}
            >
              {pending === item.jobPostingId ? "해제 중" : "관심 해제"}
            </Button>
            {failed === item.jobPostingId && (
              <p role="alert" className="basis-full text-small text-red-500">
                관심 해제를 하지 못했어요. 잠시 뒤 다시 눌러 주세요.
              </p>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
