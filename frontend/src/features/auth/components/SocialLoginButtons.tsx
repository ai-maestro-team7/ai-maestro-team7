"use client";

import { useSearchParams } from "next/navigation";
import { type ReactNode, useState } from "react";
import { getSocialProviders } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useApi } from "@/lib/useApi";
import { safeNextPath } from "../lib";
import { beginSocialLogin } from "../social";

const buttonBase =
  "relative inline-flex h-13 w-full items-center justify-center rounded-field px-5 text-btn font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40";

/** 제공자별 버튼 모양. 카카오는 카카오 로그인 버튼 색(#FEE500)과 말풍선 기호를 쓴다. */
const brands: Record<string, { tone: string; label: string; symbol: ReactNode }> = {
  kakao: {
    tone: "bg-[#FEE500] text-[#191919] hover:brightness-95",
    label: "카카오 로그인",
    symbol: (
      <svg aria-hidden viewBox="0 0 24 24" className="size-5" fill="#191919">
        <path d="M12 3C6.48 3 2 6.58 2 11c0 2.83 1.84 5.31 4.6 6.73-.2.75-.73 2.72-.84 3.14-.13.52.19.51.4.37.17-.11 2.62-1.78 3.68-2.5.7.1 1.42.16 2.16.16 5.52 0 10-3.58 10-8s-4.48-8-10-8z" />
      </svg>
    ),
  },
  google: {
    tone: "border border-grey-300 bg-white text-grey-800 hover:bg-grey-50",
    label: "Google 로그인",
    symbol: (
      <svg aria-hidden viewBox="0 0 18 18" className="size-4.5">
        <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z" />
        <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.83.86-3.04.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18z" />
        <path fill="#FBBC05" d="M3.96 10.71A5.41 5.41 0 0 1 3.68 9c0-.6.1-1.17.28-1.71V4.96H.96A9 9 0 0 0 0 9c0 1.45.35 2.83.96 4.04l3-2.33z" />
        <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.59C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58z" />
      </svg>
    ),
  },
};

/** 화면에 보이는 순서. 목록에 없는 제공자는 뒤에 붙는다. */
const ORDER = ["kakao", "google"];

/**
 * 카카오·Google 로그인 버튼 (`/api/v1/auth/social/*`).
 * 누르면 Cognito 로그인 화면으로 이동하고, 끝나면 `/login/callback/`으로 돌아온다.
 * 제공자 목록을 받지 못하면 로그인할 방법이 없으므로 안내 문구를 보여준다.
 */
export function SocialLoginButtons() {
  const next = safeNextPath(useSearchParams().get("next"));
  const [providers, reload] = useApi("auth-social-providers", getSocialProviders);
  const [pending, setPending] = useState<string>();
  const [error, setError] = useState<string>();

  if (providers.status === "loading") return <div className="h-28.5 w-full" aria-busy />;
  if (providers.status === "error" || providers.data.length === 0) {
    return (
      <div role="alert" className="flex w-full flex-col items-center gap-2">
        <p className="text-body text-grey-700">지금은 로그인할 수 없어요. 잠시 뒤 다시 시도해 주세요.</p>
        <button type="button" onClick={reload} className="text-small font-medium text-grey-700 underline underline-offset-4">
          다시 시도
        </button>
      </div>
    );
  }

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

  const rank = (id: string) => (ORDER.includes(id) ? ORDER.indexOf(id) : ORDER.length);
  const sorted = [...providers.data].sort((a, b) => rank(a.id) - rank(b.id));

  return (
    <div className="flex w-full flex-col gap-2.5">
      {sorted.map((provider) => {
        const brand = brands[provider.id];
        return (
          <button
            key={provider.id}
            type="button"
            className={cn(buttonBase, brand?.tone ?? brands.google.tone)}
            disabled={pending !== undefined}
            onClick={() => handleClick(provider.id)}
          >
            {brand && <span className="absolute left-5 inline-flex">{brand.symbol}</span>}
            {pending === provider.id ? "이동 중" : (brand?.label ?? `${provider.label} 로그인`)}
          </button>
        );
      })}
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
    </div>
  );
}
