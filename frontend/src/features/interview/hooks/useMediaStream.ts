"use client";

import { useEffect, useState } from "react";

export type MediaStatus = "idle" | "pending" | "ready" | "denied" | "unsupported";

type Result = { key: string; stream: MediaStream | null; status: "ready" | "denied" | "unsupported" };

/**
 * 마이크·카메라 스트림을 연다. 화면을 떠나면 장치를 끈다.
 * 권한을 거절했거나 장치가 없으면 `denied`, 브라우저가 지원하지 않으면(HTTP 접속 등) `unsupported`.
 */
export function useMediaStream(want: { audio: boolean; video: boolean }): { status: MediaStatus; stream: MediaStream | null } {
  const key = `${want.audio ? "a" : ""}${want.video ? "v" : ""}`;
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    if (!key) return;
    let active = true;
    let opened: MediaStream | null = null;

    if (!navigator.mediaDevices?.getUserMedia) {
      // 지원 여부는 브라우저에서만 알 수 있어 여기서 정한다
      queueMicrotask(() => active && setResult({ key, stream: null, status: "unsupported" }));
      return () => {
        active = false;
      };
    }

    navigator.mediaDevices
      .getUserMedia({
        audio: key.includes("a") ? { echoCancellation: true, noiseSuppression: true } : false,
        video: key.includes("v") ? { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" } : false,
      })
      .then(
        (stream) => {
          if (!active) {
            stream.getTracks().forEach((track) => track.stop());
            return;
          }
          opened = stream;
          setResult({ key, stream, status: "ready" });
        },
        () => active && setResult({ key, stream: null, status: "denied" }),
      );

    return () => {
      active = false;
      opened?.getTracks().forEach((track) => track.stop());
    };
  }, [key]);

  if (!key) return { status: "idle", stream: null };
  if (!result || result.key !== key) return { status: "pending", stream: null };
  return { status: result.status, stream: result.stream };
}
