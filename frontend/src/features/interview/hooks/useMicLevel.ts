"use client";

import { useEffect, useState } from "react";

const BARS = 48;
const SAMPLE_MS = 90;

/**
 * 마이크 입력 크기를 막대 높이(0~1) 목록으로 준다. 오른쪽이 가장 최근이다.
 * 소리를 녹음하거나 저장하지 않고 크기만 잰다. `active`가 false면 재지 않는다.
 */
export function useMicLevel(stream: MediaStream | null, active: boolean): number[] {
  const [levels, setLevels] = useState<number[]>([]);

  useEffect(() => {
    if (!stream || !active || stream.getAudioTracks().length === 0) return;
    const Context = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Context) return;

    const context = new Context();
    const source = context.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const buffer = new Uint8Array(analyser.fftSize);
    void context.resume().catch(() => undefined);

    const timer = window.setInterval(() => {
      analyser.getByteTimeDomainData(buffer);
      let peak = 0;
      for (const value of buffer) peak = Math.max(peak, Math.abs(value - 128));
      const level = Math.min(1, peak / 64);
      setLevels((prev) => [...prev.slice(-(BARS - 1)), level]);
    }, SAMPLE_MS);

    return () => {
      window.clearInterval(timer);
      source.disconnect();
      void context.close().catch(() => undefined);
      setLevels([]);
    };
  }, [stream, active]);

  return levels;
}

export const MIC_LEVEL_BARS = BARS;
