"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { getSocialProviders } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { safeNextPath } from "../lib";
import { beginSocialLogin } from "../social";

/**
 * Google·카카오 로그인 버튼 (`/api/v1/auth/social/*`). 제공자 목록이 비었거나 불러오지 못하면 그리지 않는다.
 * 누르면 Cognito 로그인 화면으로 이동하고, 끝나면 `/login/callback/`으로 돌아온다.
 */
export function SocialLoginButtons() {
  const next = safeNextPath(useSearchParams().get("next"));
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

  return (
    <div className="flex w-full flex-col gap-2.5 border-t border-grey-200 pt-6">
      {providers.data.map((provider) => (
        <Button
          key={provider.id}
          variant="line"
          fullWidth
          disabled={pending !== undefined}
          onClick={() => handleClick(provider.id)}
        >
          {pending === provider.id ? "이동 중" : `${provider.label}로 로그인`}
        </Button>
      ))}
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
