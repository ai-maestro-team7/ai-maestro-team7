import { ApiError, exchangeSocialCode, startSocialLogin } from "@/lib/api";
import { safeNextPath } from "./lib";
import { createCodeChallenge, createCodeVerifier, createState } from "./pkce";

/**
 * 소셜 로그인 (Cognito 외부 로그인, OAuth 2.0 인가 코드 + PKCE).
 * 로그인 화면 → `/auth/social/start` → Cognito·제공자 화면 → `/login/callback/` → `/auth/social/token`.
 * state·verifier·돌아갈 경로는 이 탭의 sessionStorage에만 두고, 돌아오면 바로 지운다.
 */
const STORAGE_KEY = "team07.social";

type PendingLogin = { state: string; codeVerifier: string; next: string };

/** 제공자 화면에서 돌아올 주소. 백엔드는 경로가 `/login/callback/`로 끝나는지 확인한다. */
export function socialRedirectUri(): string {
  return `${window.location.origin}/login/callback/`;
}

/** state·verifier를 만들어 두고 Cognito 로그인 화면 주소를 받는다. 이동은 부른 쪽에서 한다. */
export async function beginSocialLogin(provider: string, next: string): Promise<string> {
  const state = createState();
  const codeVerifier = createCodeVerifier();
  const codeChallenge = await createCodeChallenge(codeVerifier);
  const pending: PendingLogin = { state, codeVerifier, next: safeNextPath(next) };
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pending));
  return startSocialLogin(provider, socialRedirectUri(), state, codeChallenge);
}

/** 저장해 둔 값을 꺼내면서 지운다. 한 번 돌아오면 같은 값을 다시 쓰지 않는다. */
function takePendingLogin(): PendingLogin | null {
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    window.sessionStorage.removeItem(STORAGE_KEY);
    const parsed: unknown = JSON.parse(raw ?? "null");
    if (!parsed || typeof parsed !== "object") return null;
    const v = parsed as Record<string, unknown>;
    if (typeof v.state !== "string" || typeof v.codeVerifier !== "string" || typeof v.next !== "string") return null;
    return { state: v.state, codeVerifier: v.codeVerifier, next: v.next };
  } catch {
    return null;
  }
}

export type SocialCallbackFailure = "cancelled" | "invalidState" | "rejected" | "failed";

export class SocialCallbackError extends Error {
  constructor(readonly reason: SocialCallbackFailure) {
    super(reason);
    this.name = "SocialCallbackError";
  }
}

export type SocialCallbackParams = { code: string | null; state: string | null; error: string | null };

async function finishSocialLogin({ code, state, error }: SocialCallbackParams): Promise<string> {
  const pending = takePendingLogin();
  if (error) throw new SocialCallbackError(error === "access_denied" ? "cancelled" : "failed");
  // state가 없거나 다르면 이 탭에서 시작한 로그인이 아니다. 코드를 교환하지 않는다.
  if (!pending || !state || state !== pending.state) throw new SocialCallbackError("invalidState");
  if (!code) throw new SocialCallbackError("failed");
  try {
    await exchangeSocialCode(code, socialRedirectUri(), pending.codeVerifier);
  } catch (e) {
    throw new SocialCallbackError(e instanceof ApiError && e.status === 401 ? "rejected" : "failed");
  }
  return safeNextPath(pending.next);
}

/** 같은 응답은 한 번만 처리한다. React 개발 모드에서 effect가 두 번 돌아도 코드를 두 번 교환하지 않는다. */
const handled = new Map<string, Promise<string>>();

/** 돌아온 주소의 값을 확인하고 토큰으로 바꾼다. 성공하면 돌아갈 경로를 준다. */
export function completeSocialLogin(params: SocialCallbackParams): Promise<string> {
  const key = JSON.stringify(params);
  let result = handled.get(key);
  if (!result) {
    result = finishSocialLogin(params);
    handled.set(key, result);
  }
  return result;
}

export function socialCallbackMessage(reason: SocialCallbackFailure): string {
  switch (reason) {
    case "cancelled":
      return "로그인을 취소했어요.";
    case "invalidState":
      return "로그인 요청을 확인하지 못했어요. 처음부터 다시 시도해 주세요.";
    case "rejected":
      return "로그인하지 못했어요. 처음부터 다시 시도해 주세요.";
    case "failed":
      return "로그인하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
  }
}
