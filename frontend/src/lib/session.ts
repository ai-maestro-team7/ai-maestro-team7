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
    typeof v.expiresAt === "number"
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

/** 탭에 남기는 사용자별 값 (채팅 대화 ID, 면접 인계 자소서). 로그아웃·계정 변경 때 지운다 */
const USER_TAB_KEYS = ["team07.interviewHandoff", "team07.chatSessionId"];

function clearUserTabData(): void {
  for (const key of USER_TAB_KEYS) window.sessionStorage.removeItem(key);
}

/** 토큰의 sub (사용자 고유 ID). 소셜 로그인은 아이디가 "Google 계정"처럼 같아서 아이디로 구분할 수 없다 */
export function sessionOwner(session: Session | null = readSession()): string | null {
  if (!session) return null;
  try {
    const raw = session.accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(window.atob(raw.padEnd(Math.ceil(raw.length / 4) * 4, "="))) as { sub?: string };
    return claims.sub || session.username;
  } catch {
    return session.username;
  }
}

export function saveSession(session: Session): void {
  if (sessionOwner(readSession()) !== sessionOwner(session)) clearUserTabData(); // 다른 계정으로 바뀌면 지운다
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

export function clearSession(): void {
  clearUserTabData();
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
