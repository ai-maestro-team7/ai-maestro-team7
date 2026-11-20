import { Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import { MIC_LEVEL_BARS } from "../hooks/useMicLevel";
import { formatTimer } from "../lib";

type RecorderProps = {
  /** 녹음한 시간(초) */
  elapsed: number;
  /** 제한 시간(초) */
  limit: number;
  /** 마이크 입력 크기 0~1 (오른쪽이 최근) */
  levels: number[];
  /** 남은 시간 알림 ("30초 남았어요") */
  notice?: string;
};

/** 녹음 상태 상자: 경과 시간과 마이크 입력 크기를 보여준다. */
export function Recorder({ elapsed, limit, levels, notice }: RecorderProps) {
  const bars = [...Array<number>(Math.max(0, MIC_LEVEL_BARS - levels.length)).fill(0), ...levels];
  return (
    <Panel className="flex flex-col gap-3.5 p-5">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2">
          <span aria-hidden className="size-2 animate-pulse rounded-full bg-red-500" />
          <span className="text-body font-bold text-grey-900">녹음 중</span>
          {notice && (
            <span role="status" className="text-small font-medium text-red-500">
              {notice}
            </span>
          )}
        </p>
        <p className="text-h2 font-bold text-grey-900 tabular-nums">
          <span className="sr-only">경과 시간 </span>
          <span role="timer">{formatTimer(elapsed)}</span>
          <span className="text-body font-medium text-grey-500"> / {formatTimer(limit)}</span>
        </p>
      </div>
      <div aria-hidden className="flex h-11 items-center gap-1">
        {bars.map((level, index) => (
          <span
            key={index}
            className={cn("w-0.75 shrink-0 rounded-full", level > 0.04 ? "bg-blue-500" : "bg-grey-300")}
            style={{ height: Math.max(4, Math.round(level * 40)) }}
          />
        ))}
      </div>
    </Panel>
  );
}
