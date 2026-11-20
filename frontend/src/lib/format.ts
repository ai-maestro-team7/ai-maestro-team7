const DAY_MS = 24 * 60 * 60 * 1000;

/** `2026-12-05` → `12.05` */
export function formatMonthDay(isoDate: string): string {
  const [, month, day] = isoDate.split("-");
  return `${month}.${day}`;
}

/** 기준일(asOf)에서 마감일까지 남은 날을 `D-15` 형태로 만든다. 같은 날이면 `D-day`. */
export function formatDday(isoDate: string, asOf: string): string {
  const diff = Math.round((Date.parse(`${isoDate}T00:00:00+09:00`) - Date.parse(`${asOf}T00:00:00+09:00`)) / DAY_MS);
  if (diff === 0) return "D-day";
  return diff > 0 ? `D-${diff}` : "마감";
}

/** `2026-11-20` → `2026.11.20` */
export function formatDate(isoDate: string): string {
  return isoDate.replaceAll("-", ".");
}
