"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { type ReactNode, Suspense, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/Button";
import { loginHref } from "../lib";
import { useUsername } from "../useUsername";
import { ApiLoading } from "./ApiFallback";

const subscribeNothing = () => () => {};

/** 정적 HTML을 받은 뒤 브라우저가 세션을 읽기 전까지는 false다. 로그인한 사람에게 로그인 안내가 잠깐 보이지 않게 한다. */
function useHydrated(): boolean {
  return useSyncExternalStore(
    subscribeNothing,
    () => true,
    () => false,
  );
}

/**
 * 로그인해야 쓰는 화면 (맞춤형 공고, 청년 지원 정책). 로그인 전이면 안내와 로그인 버튼을, 로그인했으면 children을 그린다.
 * 로그인하면 지금 화면(검색 조건 포함)으로 돌아온다.
 */
export function LoginGate({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  const hydrated = useHydrated();
  const username = useUsername();
  if (!hydrated) return <ApiLoading />;
  if (username) return <>{children}</>;
  return (
    <Suspense fallback={<ApiLoading />}>
      <LoginRequired title={title} description={description} />
    </Suspense>
  );
}

function LoginRequired({ title, description }: { title: string; description: string }) {
  const pathname = usePathname();
  const query = useSearchParams().toString();
  const current = query ? `${pathname}?${query}` : pathname;
  return (
    <div className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-14 text-center">
      <p className="text-body font-bold text-grey-900">{title}</p>
      <p className="text-small text-grey-600">{description}</p>
      <Button href={loginHref(current)} size="M">
        로그인
      </Button>
    </div>
  );
}
