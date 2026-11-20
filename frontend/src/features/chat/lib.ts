import { sessionOwner } from "@/lib/session";
import type { InterviewHandoff } from "./types";

const HANDOFF_KEY = "team07.interviewHandoff";
const HANDOFF_EVENT = "team07:interviewHandoff";

/** 채팅에서 면접 화면으로 넘길 값. 같은 탭 안에서만 쓰도록 sessionStorage에 둔다. */
export function writeHandoff(handoff: Omit<InterviewHandoff, "owner">): void {
  // 주인(토큰 sub)을 같이 적고, 읽을 때 지금 로그인한 사용자와 같을 때만 쓴다 (로그아웃 때도 지운다)
  window.sessionStorage.setItem(HANDOFF_KEY, JSON.stringify({ ...handoff, owner: sessionOwner() }));
  window.dispatchEvent(new Event(HANDOFF_EVENT));
}

/** useSyncExternalStore용 스냅샷. 같은 값이면 같은 문자열을 돌려줘야 해서 원문 그대로 준다. */
export function readHandoffRaw(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(HANDOFF_KEY);
}

export function parseHandoff(raw: string | null): InterviewHandoff | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<InterviewHandoff> | null;
    if (!value || value.source !== "chat" || typeof value.job !== "string") return null;
    const owner = sessionOwner();
    if (!owner || value.owner !== owner) return null; // 다른 사용자가 남긴 자소서는 쓰지 않는다
    return {
      job: value.job,
      coverLetter: typeof value.coverLetter === "string" ? value.coverLetter : undefined,
      documentId: typeof value.documentId === "string" ? value.documentId : undefined,
      documentTitle: typeof value.documentTitle === "string" ? value.documentTitle : undefined,
      posting:
        value.posting && typeof value.posting.jobPostingId === "string"
          ? {
              jobPostingId: value.posting.jobPostingId,
              title: typeof value.posting.title === "string" ? value.posting.title : undefined,
              organization: typeof value.posting.organization === "string" ? value.posting.organization : undefined,
            }
          : undefined,
      source: "chat",
      owner,
    };
  } catch {
    return null;
  }
}

export function subscribeHandoff(onChange: () => void): () => void {
  window.addEventListener(HANDOFF_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(HANDOFF_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

/** 홈과 새 대화에서 보여 주는 예시 질문 */
/** 홈 채팅창 예시. "이력서 붙여넣고 찾기"와 함께 세 개가 한 줄에 들어가게 둘만 둔다 */
export const HOME_EXAMPLES = ["부산 데이터 분석 신입 공고 찾아줘", "내가 받을 수 있는 청년정책 알려줘"];

export const CHAT_EXAMPLES = [
  "부산 데이터 분석 신입 공고 찾아줘",
  "연봉 3천 이상 부산 공기업 공고 알려줘",
  "내가 받을 수 있는 청년정책 알려줘",
];

/** 채팅 화면 주소. 대화 ID가 없으면 새 대화다 (정적 내보내기라 경로 대신 `?s=`를 쓴다) */
export function chatHref(sessionId?: string | null): string {
  return sessionId ? `/chat/?s=${encodeURIComponent(sessionId)}` : "/chat/";
}

/** 면접 설정 화면 주소. 공고와 함께 가면 `posting`을 붙인다. 면접 화면은 이 값이 있을 때만 공고 올리기를 끈다 (#167) */
export function interviewHref(job: string, jobPostingId?: string): string {
  const params = new URLSearchParams({ job, mode: "voice" });
  if (jobPostingId) params.set("posting", jobPostingId);
  return `/interview/?${params.toString()}`;
}

/** 면접 행동에 실린 공고를 인계 값으로 */
export function linkedPosting(action: {
  jobPostingId?: string;
  postingTitle?: string;
  postingOrganization?: string;
}): { jobPostingId: string; title?: string; organization?: string } | undefined {
  return action.jobPostingId
    ? { jobPostingId: action.jobPostingId, title: action.postingTitle, organization: action.postingOrganization }
    : undefined;
}

export const POLICY_STATUS_LABEL: Record<string, string> = {
  ELIGIBLE: "자격이 맞아요",
  CHECK_NEEDED: "확인이 필요해요",
  NOT_ELIGIBLE: "자격이 맞지 않아요",
  AFTER_EMPLOYMENT: "취업하면 받을 수 있어요",
};

export function asOfLabel(value?: string): string | null {
  return value ? `기준 ${value.slice(0, 10)}` : null;
}
