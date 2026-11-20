"use client";

import { useEffect, useState } from "react";
import { ApiError, AUTH_REQUIRED } from "@/lib/api";
import { getInterviewStatus } from "../api";
import { RULES } from "../data";
import type { InterviewStatusBody } from "../types";

type Polled = { sessionId: string; body: InterviewStatusBody | null; error: ApiError | null };

/**
 * `/status`를 2초마다 조회한다. COMPLETED·FAILED가 되면 멈춘다 (docs/개발계획서3.md §5.4).
 * 한 번 실패했다고 면접을 끊지 않는다. 로그인이 풀렸거나 세션이 없을 때만 오류로 멈춘다.
 */
export function useInterviewStatus(sessionId: string | null): { status: InterviewStatusBody | null; error: ApiError | null } {
  const [polled, setPolled] = useState<Polled | null>(null);

  useEffect(() => {
    if (!sessionId) return;
    let active = true;
    let timer: number | undefined;

    async function tick() {
      try {
        const body = await getInterviewStatus(sessionId as string);
        if (!active) return;
        setPolled({ sessionId: sessionId as string, body, error: null });
        if (body.status === "COMPLETED" || body.status === "FAILED") return;
      } catch (e) {
        if (!active) return;
        const fatal = e instanceof ApiError && (e.code === AUTH_REQUIRED || e.status === 404 || e.status === 403);
        if (fatal) {
          setPolled((prev) => ({ sessionId: sessionId as string, body: prev?.sessionId === sessionId ? prev.body : null, error: e }));
          return;
        }
      }
      timer = window.setTimeout(tick, RULES.pollMs);
    }

    void tick();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [sessionId]);

  if (!sessionId || polled?.sessionId !== sessionId) return { status: null, error: null };
  return { status: polled.body, error: polled.error };
}
