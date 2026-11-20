/** 진행률 줄: 왼쪽 글(Small B, grey-800) + 4px 막대 (blue-500 / grey-200). */
export function ProgressBar({ label, value }: { label: string; value: number }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="flex w-full items-center gap-3">
      <span className="shrink-0 text-small font-bold text-grey-800">{label}</span>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="h-1 flex-1 overflow-hidden rounded-full bg-grey-200"
      >
        <div className="h-full rounded-full bg-blue-500" style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
