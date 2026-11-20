"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ApiLoading } from "./ApiFallback";
import { completeSocialLogin, SocialCallbackError, socialCallbackMessage } from "../social";

/** 제공자 화면에서 돌아온 뒤 인가 코드를 토큰으로 바꾸고 원래 보던 화면으로 보낸다. */
export function SocialCallback() {
  const router = useRouter();
  const params = useSearchParams();
  const code = params.get("code");
  const state = params.get("state");
  const providerError = params.get("error");
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    completeSocialLogin({ code, state, error: providerError }).then(
      (next) => active && router.replace(next),
      (e: unknown) =>
        active && setError(socialCallbackMessage(e instanceof SocialCallbackError ? e.reason : "failed")),
    );
    return () => {
      active = false;
    };
  }, [code, state, providerError, router]);

  if (!error) return <ApiLoading label="로그인하는 중" />;

  return (
    <div
      role="alert"
      className="flex w-full flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center"
    >
      <p className="text-body font-bold text-grey-900">{error}</p>
      <Button href="/login/" size="M">
        로그인 화면으로
      </Button>
    </div>
  );
}
