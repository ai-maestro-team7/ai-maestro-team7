/**
 * 로그인 뒤 돌아갈 주소. 같은 사이트 경로(`/`로 시작, `//` 아님)만 받는다 (열린 리디렉트 방지).
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  return next;
}

/** 지금 보고 있는 화면으로 돌아오는 로그인 주소 */
export function loginHref(currentPath: string): string {
  if (currentPath === "/" || currentPath.startsWith("/login")) return "/login/";
  return `/login/?next=${encodeURIComponent(currentPath)}`;
}
