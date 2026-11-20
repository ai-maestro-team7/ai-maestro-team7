"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

export type ApiState<T> =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "success"; data: T };

type Settled<T> = { key: string; result: ApiState<T> };

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "NETWORK_ERROR", "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.", true);
}

/**
 * 화면에서 API를 부른다. `key`가 바뀌거나 `reload()`를 부르면 다시 부르고, 응답이 오기 전에는 loading이다.
 * 늦게 온 이전 응답은 버린다. `key`가 null이면 부르지 않는다 (예: 주소에 ID가 없을 때).
 */
export function useApi<T>(key: string | null, fetcher: () => Promise<T>): [ApiState<T>, () => void] {
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const fullKey = key === null ? null : `${key}#${attempt}`;

  useEffect(() => {
    if (fullKey === null) return;
    let active = true;
    fetcher().then(
      (data) => active && setSettled({ key: fullKey, result: { status: "success", data } }),
      (error: unknown) => active && setSettled({ key: fullKey, result: { status: "error", error: toApiError(error) } }),
    );
    return () => {
      active = false;
    };
    // fetcher는 렌더마다 새로 만들어지므로 key로만 다시 부른다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fullKey]);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);
  if (fullKey === null || !settled || settled.key !== fullKey) return [{ status: "loading" }, reload];
  return [settled.result, reload];
}
