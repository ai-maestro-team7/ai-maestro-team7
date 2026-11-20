"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { AUTH_REQUIRED, type ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { loginHref } from "../lib";

/** API 화면의 불러오는 중 자리 */
export function ApiLoading({ className, label = "불러오는 중" }: { className?: string; label?: string }) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "flex w-full items-center justify-center border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-small text-grey-600",
        className,
      )}
    >
      {label}
    </div>
  );
}

/** API 오류 안내. 로그인이 필요하면 로그인 버튼을, 다시 시도할 수 있으면 다시 시도 버튼을 보여준다. */
export function ApiErrorNotice({
  error,
  onRetry,
  className,
}: {
  error: ApiError;
  onRetry?: () => void;
  className?: string;
}) {
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const current = query ? `${pathname}?${query}` : pathname;
  const needsLogin = error.code === AUTH_REQUIRED;

  return (
    <div
      role="alert"
      className={cn(
        "flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center",
        className,
      )}
    >
      <p className="text-body font-bold text-grey-900">
        {needsLogin ? "로그인하면 나에게 맞는 공고와 정책을 볼 수 있어요" : error.message}
      </p>
      {needsLogin ? (
        <Button href={loginHref(current)} size="M">
          로그인
        </Button>
      ) : (
        <>
          {error.code === "PROFILE_INCOMPLETE" && (
            <Button href={`/profile/?next=${encodeURIComponent(current)}`} size="M">
              기본 정보 입력하기
            </Button>
          )}
          {error.requestId && <p className="text-small text-grey-500">요청 번호 {error.requestId}</p>}
          {error.retryable && onRetry && (
            <Button variant="line" size="M" onClick={onRetry}>
              다시 시도
            </Button>
          )}
        </>
      )}
    </div>
  );
}
