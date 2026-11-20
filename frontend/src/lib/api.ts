import { clearSession, readSession, saveSession, type Session } from "./session";
import type { BasicProfile, BasicProfileInput } from "@/features/profile/types";

/**
 * 팀 공통 API 호출 (docs/api.md).
 * 배포에서는 CloudFront가 같은 주소의 `/api/*`를 API Gateway로 넘기므로 기본 주소는 빈 문자열이다.
 * 로컬 개발(`npm run dev`)에서만 `.env.local`의 `NEXT_PUBLIC_API_BASE`로 API Gateway 주소를 넣는다 (커밋 금지).
 */
const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/+$/, "");

/** 공통 오류 형식 `error{code, message, requestId, retryable}` (docs/api.md §5) */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable = false,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** 로그인이 필요하거나 토큰을 갱신하지 못했을 때 */
export const AUTH_REQUIRED = "AUTH_REQUIRED";

type TokenResponse = { accessToken: string; refreshToken?: string; expiresIn: number };

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as { error?: { code?: string; message?: string; retryable?: boolean; requestId?: string } };
    if (body.error?.code) {
      return new ApiError(
        response.status,
        body.error.code,
        body.error.message ?? "요청을 처리하지 못했어요.",
        body.error.retryable ?? false,
        body.error.requestId,
      );
    }
  } catch {
    // JSON이 아닌 오류 (API Gateway 401 `{"message":"Unauthorized"}` 등)
  }
  if (response.status === 401) return new ApiError(401, AUTH_REQUIRED, "다시 로그인해 주세요.");
  if (response.status === 404) return new ApiError(404, "NOT_FOUND", "찾을 수 없어요.");
  return new ApiError(response.status, "HTTP_ERROR", "잠시 뒤 다시 시도해 주세요.", response.status >= 500);
}

function sessionFrom(tokens: TokenResponse, username: string, refreshToken?: string): Session {
  return {
    username,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken ?? refreshToken ?? "",
    expiresAt: Date.now() + tokens.expiresIn * 1000,
  };
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

/** `POST /api/v1/auth/login` (토큰 없이). 실패는 아이디·비밀번호 구분 없이 401 INVALID_CREDENTIALS. */
export async function login(username: string, password: string): Promise<Session> {
  const tokens = await postJson<TokenResponse>("/api/v1/auth/login", { username, password });
  const session = sessionFrom(tokens, username);
  saveSession(session);
  return session;
}

/** 소셜 로그인 제공자 (Cognito 외부 로그인). `id`는 `google`·`kakao`, `label`은 화면에 보일 이름 */
export type SocialProvider = { id: string; label: string };

/** `GET /api/v1/auth/social/providers` (토큰 없이). 설정되지 않았으면 빈 목록이다. */
export async function getSocialProviders(): Promise<SocialProvider[]> {
  const response = await fetch(`${API_BASE}/api/v1/auth/social/providers`);
  if (!response.ok) throw await toApiError(response);
  const body = (await response.json()) as { providers?: SocialProvider[] };
  return body.providers ?? [];
}

/**
 * `POST /api/v1/auth/social/start` (토큰 없이). Cognito 로그인 화면 주소(`authorizeUrl`)를 받는다.
 * 제공자에게는 `openid`만 요청한다 (이름·이메일을 받지 않는다).
 */
export async function startSocialLogin(
  provider: string,
  redirectUri: string,
  state: string,
  codeChallenge: string,
): Promise<string> {
  const { authorizeUrl } = await postJson<{ authorizeUrl: string }>("/api/v1/auth/social/start", {
    provider,
    redirectUri,
    state,
    codeChallenge,
  });
  return authorizeUrl;
}

/**
 * `POST /api/v1/auth/social/token` (토큰 없이). 인가 코드를 토큰으로 바꾸고 세션을 저장한다.
 * `username`은 "Google 계정" 같은 고정 문구다. 코드가 틀리거나 만료면 401 INVALID_CREDENTIALS.
 */
export async function exchangeSocialCode(code: string, redirectUri: string, codeVerifier: string): Promise<Session> {
  const tokens = await postJson<TokenResponse & { username?: string }>("/api/v1/auth/social/token", {
    code,
    redirectUri,
    codeVerifier,
  });
  const session = sessionFrom(tokens, tokens.username ?? "소셜 계정");
  saveSession(session);
  return session;
}

/** 여러 요청이 동시에 401을 받아도 갱신은 한 번만 한다. */
let refreshing: Promise<Session | null> | null = null;

async function refresh(session: Session): Promise<Session | null> {
  if (!session.refreshToken) return null;
  refreshing ??= postJson<TokenResponse>("/api/v1/auth/refresh", { refreshToken: session.refreshToken })
    .then((tokens) => {
      const next = sessionFrom(tokens, session.username, session.refreshToken);
      saveSession(next);
      return next;
    })
    .catch(() => null)
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

/** 만료 1분 전부터는 미리 갱신한다. */
const REFRESH_MARGIN_MS = 60_000;

/**
 * 토큰이 필요한 API 호출. 401이면 한 번 갱신하고 다시 부른다.
 * 갱신도 안 되면 세션을 지우고 `AUTH_REQUIRED` 오류를 던진다 (화면은 로그인 안내를 보여준다).
 */
export async function apiGet<T>(path: string, query?: Record<string, string | number | undefined>): Promise<T> {
  let session = readSession();
  if (!session) throw new ApiError(401, AUTH_REQUIRED, "로그인이 필요해요.");
  if (session.expiresAt - Date.now() < REFRESH_MARGIN_MS) session = (await refresh(session)) ?? session;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const url = `${API_BASE}${path}${params.size ? `?${params}` : ""}`;
  const call = (token: string) => fetch(url, { headers: { authorization: `Bearer ${token}` } });

  let response = await call(session.accessToken);
  if (response.status === 401) {
    const renewed = await refresh(session);
    if (!renewed) {
      clearSession();
      throw new ApiError(401, AUTH_REQUIRED, "다시 로그인해 주세요.");
    }
    response = await call(renewed.accessToken);
  }
  if (!response.ok) {
    const error = await toApiError(response);
    if (error.code === AUTH_REQUIRED) clearSession();
    throw error;
  }
  return (await response.json()) as T;
}

/** `GET /api/v1/me/profile`. 아직 프로필이 없으면(404) null. */
export async function getMyProfile(): Promise<BasicProfile | null> {
  try {
    return await apiGet<BasicProfile>("/api/v1/me/profile");
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  }
}

/**
 * 토큰이 필요한 쓰기 호출 (POST·PUT). 본문은 JSON 값이거나 `FormData`(녹음·이미지 업로드)다.
 * 401이면 한 번 갱신하고 다시 보낸다. `FormData`는 브라우저가 경계 문자열을 붙이므로 content-type을 직접 넣지 않는다.
 */
export async function apiSend<T>(method: "POST" | "PUT", path: string, body: FormData | object): Promise<T> {
  let session = readSession();
  if (!session) throw new ApiError(401, AUTH_REQUIRED, "로그인이 필요해요.");
  if (session.expiresAt - Date.now() < REFRESH_MARGIN_MS) session = (await refresh(session)) ?? session;

  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  const call = (token: string) =>
    fetch(`${API_BASE}${path}`, {
      method,
      headers: { authorization: `Bearer ${token}`, ...(isForm ? {} : { "content-type": "application/json" }) },
      body: isForm ? body : JSON.stringify(body),
    });

  let response = await call(session.accessToken);
  if (response.status === 401) {
    const renewed = await refresh(session);
    if (!renewed) {
      clearSession();
      throw new ApiError(401, AUTH_REQUIRED, "다시 로그인해 주세요.");
    }
    response = await call(renewed.accessToken);
  }
  if (!response.ok) throw await toApiError(response);
  return (await response.json()) as T;
}

/** `PUT /api/v1/me/profile`. 보낸 항목만 바뀌고 null을 보내면 그 항목이 지워진다. */
export function saveMyProfile(profile: BasicProfileInput): Promise<BasicProfile> {
  return apiSend<BasicProfile>("PUT", "/api/v1/me/profile", profile);
}
