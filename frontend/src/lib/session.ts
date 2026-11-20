/**
 * 로그인 세션 (Cognito 토큰). 정적 내보내기라 서버 쿠키를 쓸 수 없어 브라우저 localStorage에 둔다.
 * 데모 계정만 쓰는 해커톤 시연용이다. 화면에 사용자 입력 HTML을 넣지 않아 XSS 경로를 만들지 않는다.
 */
export type Session = {
  username: string;
  accessToken: string;
  refreshToken: string;
  /** 액세스 토큰 만료 시각 (epoch ms) */
  expiresAt: number;
  /** 개발 모드로 로그인했을 때만 true. 이 값이 생기기 전에 저장된 세션에는 없다. */
  devMode?: boolean;
};

const STORAGE_KEY = "team07.session";
const CHANGE_EVENT = "team07:session";

function isSession(value: unknown): value is Session {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.username === "string" &&
    typeof v.accessToken === "string" &&
    typeof v.refreshToken === "string" &&
    typeof v.expiresAt === "number" &&
    (v.devMode === undefined || typeof v.devMode === "boolean")
  );
}

export function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null");
    return isSession(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveSession(session: Session): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function clearSession(): void {
  window.localStorage.removeItem(STORAGE_KEY);
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

/** 로그인·로그아웃(다른 탭 포함)을 구독한다. `useSyncExternalStore`용. */
export function subscribeSession(callback: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) callback();
  };
  window.addEventListener(CHANGE_EVENT, callback);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(CHANGE_EVENT, callback);
    window.removeEventListener("storage", onStorage);
  };
}

/** 화면에 보여줄 아이디. 세션 객체가 매번 새로 만들어지지 않게 문자열만 구독한다. */
export function readUsername(): string | null {
  return readSession()?.username ?? null;
}

/** 개발 모드로 로그인한 세션인지. `readUsername`처럼 값만 구독하게 불리언으로 준다. */
export function readDevMode(): boolean {
  return readSession()?.devMode === true;
}

/**
 * 사용자별 저장소 키에 붙이는 값. 액세스 토큰의 `sub`(Cognito 사용자 ID)를 쓰고, 읽지 못하면 아이디를 쓴다.
 * 로그아웃했다가 다시 들어와도 같은 값이라 그 사용자의 기록을 다시 찾을 수 있다.
 */
export function sessionOwner(session: Pick<Session, "accessToken" | "username">): string {
  try {
    const payload = session.accessToken.split(".")[1];
    const raw = payload.replace(/-/g, "+").replace(/_/g, "/");
    const normalized = raw.padEnd(Math.ceil(raw.length / 4) * 4, "=");
    const claims = JSON.parse(window.atob(normalized)) as { sub?: string };
    return claims.sub || session.username;
  } catch {
    return session.username;
  }
}
