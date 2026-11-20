"use client";

import { useEffect, useSyncExternalStore } from "react";
import { useUsername } from "@/features/auth/useUsername";
import { apiGet, apiSend } from "@/lib/api";

/** 저장한 공고 한 건 (`GET /api/v1/opportunities/saved`) */
export type SavedJob = {
  jobPostingId: string;
  /** INTEREST: 관심 · TARGET: 지원 목표 */
  kind: "INTEREST" | "TARGET";
  status: string;
  isBusan: boolean;
  savedAt: string;
  title?: string;
  organization?: string;
  closesAt?: string;
};

const BASE = "/api/v1/opportunities/saved";

export function getSavedJobs(): Promise<{ items: SavedJob[] }> {
  return apiGet<{ items: SavedJob[] }>(BASE);
}

// ---------------------------------------------------------------- 저장한 공고 ID (화면들이 같이 본다)

type Store = { owner: string | null; ids: ReadonlySet<string>; loading: boolean };
const EMPTY: ReadonlySet<string> = new Set();
let store: Store = { owner: null, ids: EMPTY, loading: false };
const listeners = new Set<() => void>();

function update(next: Store) {
  store = next;
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 로그인한 사용자의 저장 목록을 한 번 읽어 둔다. 사용자가 바뀌면 다시 읽는다. */
function load(owner: string | null) {
  if (store.owner === owner && (store.loading || store.ids !== EMPTY || owner === null)) return;
  if (owner === null) {
    update({ owner: null, ids: EMPTY, loading: false });
    return;
  }
  update({ owner, ids: EMPTY, loading: true });
  getSavedJobs().then(
    (body) => store.owner === owner && update({ owner, ids: new Set(body.items.map((item) => item.jobPostingId)), loading: false }),
    // 목록을 못 읽어도 화면은 그대로 쓴다. 저장 표시만 비어 보인다
    () => store.owner === owner && update({ owner, ids: new Set(), loading: false }),
  );
}

/** 읽어 둔 저장 목록을 버린다. 저장 표시가 필요한 화면이 다음에 열릴 때 다시 읽는다 (개발 모드의 유저 정보 초기화). */
export function forgetSavedIds(): void {
  update({ owner: null, ids: EMPTY, loading: false });
}

/** 저장한 공고 ID 모음. 로그인 전이면 비어 있다. */
export function useSavedIds(): ReadonlySet<string> {
  const username = useUsername();
  useEffect(() => load(username), [username]);
  return useSyncExternalStore(
    subscribe,
    () => store.ids,
    () => EMPTY,
  );
}

/**
 * 공고를 저장한다 (`POST /saved`, 관심 공고). 같은 요청이 두 번 가도 한 번만 저장되게 `Idempotency-Key`를 붙인다.
 * 저장을 푸는 것은 `unsaveJob`이다.
 */
export async function saveJob(jobPostingId: string): Promise<void> {
  // 키에는 `#`을 넣지 않는다 (ai/busan-opportunity/API.md)
  const key = `save-${jobPostingId}-${crypto.randomUUID()}`.replaceAll("#", "-");
  await apiSend("POST", BASE, { jobPostingId, kind: "INTEREST" }, { "Idempotency-Key": key });
  update({ ...store, ids: new Set(store.ids).add(jobPostingId) });
}

/**
 * 저장을 푼다 (`DELETE /saved/{id}`). 목표 공고의 마감 일정도 서버가 지운다. 워크스페이스(분석·첨삭 기록)는 남는다.
 * 이미 풀려 있어도 오류가 아니라서 여러 번 불러도 된다.
 */
export async function unsaveJob(jobPostingId: string): Promise<void> {
  await apiSend("DELETE", `${BASE}/${encodeURIComponent(jobPostingId)}`, undefined);
  const ids = new Set(store.ids);
  ids.delete(jobPostingId);
  update({ ...store, ids });
}
