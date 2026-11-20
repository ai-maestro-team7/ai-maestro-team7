"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { getSocialProviders } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/useApi";
import { safeNextPath } from "../lib";
import { beginSocialLogin } from "../social";

const buttonBase =
  "inline-flex h-12 shrink-0 items-center justify-center whitespace-nowrap rounded-field px-5 text-btn font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-40";

/** 제공자별 버튼 색. 카카오는 카카오 로그인 버튼 색(#FEE500)을 쓰고, 그 밖은 Line 버튼과 같다. */
const buttonTone: Record<string, string> = {
  kakao: "bg-[#FEE500] text-[#191919] hover:brightness-95",
};
const defaultTone = "border border-grey-300 bg-white text-grey-800 hover:bg-grey-50";

type SocialLoginButtonsProps = {
  /** stack: 로그인 화면(세로, 위에 구분선) · row: 홈(가로로 나란히) */
  layout?: "stack" | "row";
  /** 로그인 뒤 돌아갈 경로. 없으면 주소의 `?next=`를 쓴다. */
  next?: string;
};

/**
 * Google·카카오 로그인 버튼 (`/api/v1/auth/social/*`). 제공자 목록이 비었거나 불러오지 못하면 그리지 않는다.
 * 누르면 Cognito 로그인 화면으로 이동하고, 끝나면 `/login/callback/`으로 돌아온다.
 */
export function SocialLoginButtons({ layout = "stack", next: nextProp }: SocialLoginButtonsProps) {
  const queryNext = useSearchParams().get("next");
  const next = safeNextPath(nextProp ?? queryNext);
  const [providers] = useApi("auth-social-providers", getSocialProviders);
  const [pending, setPending] = useState<string>();
  const [error, setError] = useState<string>();

  if (providers.status !== "success" || providers.data.length === 0) return null;

  async function handleClick(provider: string) {
    setPending(provider);
    setError(undefined);
    try {
      window.location.assign(await beginSocialLogin(provider, next));
    } catch {
      setError("로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요.");
      setPending(undefined);
    }
  }

  const row = layout === "row";
  return (
    <div className={cn("flex", row ? "flex-col gap-2" : "w-full flex-col gap-2.5 border-t border-grey-200 pt-6")}>
      <div className={cn("flex gap-2.5", row ? "flex-wrap" : "w-full flex-col")}>
        {providers.data.map((provider) => (
          <button
            key={provider.id}
            type="button"
            className={cn(buttonBase, buttonTone[provider.id] ?? defaultTone, !row && "w-full")}
            disabled={pending !== undefined}
            onClick={() => handleClick(provider.id)}
          >
            {pending === provider.id ? "이동 중" : `${provider.label}로 로그인`}
          </button>
        ))}
      </div>
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
