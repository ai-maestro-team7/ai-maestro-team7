/**
 * OAuth 2.0 PKCE 값 (RFC 7636). 브라우저 Web Crypto만 쓰고 외부 라이브러리는 쓰지 않는다.
 * verifier·state는 URL에 그대로 실을 수 있게 base64url(패딩 없음)로 만든다.
 */

/** 32바이트 → base64url 43자 (RFC 7636 §4.1의 최소 길이) */
const VERIFIER_BYTES = 32;
/** 16바이트 → base64url 22자 */
const STATE_BYTES = 16;

function base64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function randomBase64Url(byteLength: number): string {
  return base64Url(crypto.getRandomValues(new Uint8Array(byteLength)));
}

/** 로그인 요청과 돌아온 응답을 짝짓는 값 (CSRF 방지) */
export function createState(): string {
  return randomBase64Url(STATE_BYTES);
}

/** 토큰 교환 때만 보내는 비밀 값. 브라우저 sessionStorage에만 둔다. */
export function createCodeVerifier(): string {
  return randomBase64Url(VERIFIER_BYTES);
}

/** `code_challenge_method=S256`: base64url(SHA-256(verifier)) */
export async function createCodeChallenge(verifier: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
  return base64Url(new Uint8Array(digest));
}
