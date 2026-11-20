"use client";

import { useEffect, useState } from "react";
import { Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import { WAVEFORM_BARS, WAVEFORM_SPOKEN } from "../data";
import { formatTimer } from "../lib";

/**
 * 녹음 상태 상자. 시연에서는 실제로 녹음하지 않고, 화면 타이머만 1초씩 올라간다.
 * 질문이 바뀔 때 `key`를 바꿔 다시 마운트하면 타이머가 0부터 시작한다.
 */
export function Recorder() {
  const [seconds, setSeconds] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <Panel className="flex flex-col gap-3.5 p-5">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2">
          <span aria-hidden className="size-2 rounded-full bg-red-500" />
          <span className="text-body font-bold text-grey-900">녹음 중</span>
          <span className="text-small text-grey-500">예시</span>
        </p>
        <p className="text-h2 font-bold text-grey-900 tabular-nums">
          <span className="sr-only">경과 시간 </span>
          <span role="timer">{formatTimer(seconds)}</span>
        </p>
      </div>
      <div aria-hidden className="flex h-11 items-center gap-1">
        {WAVEFORM_BARS.map((height, index) => (
          <span
            key={index}
            className={cn("w-0.75 shrink-0 rounded-full", index < WAVEFORM_SPOKEN ? "bg-blue-500" : "bg-grey-300")}
            style={{ height }}
          />
        ))}
      </div>
      <p className="text-small text-grey-600">질문을 읽어 드린 뒤에 녹음이 시작돼요.</p>
    </Panel>
  );
}
