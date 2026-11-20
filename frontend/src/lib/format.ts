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

/** 서버 시각 `2026-11-20T14:25:00+09:00` → `2026.11.20 14:25` (한국 시간으로 내려오는 값을 그대로 자른다, D-29) */
export function formatDateTime(isoDateTime: string): string {
  const match = /^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2}))?/.exec(isoDateTime);
  if (!match) return isoDateTime;
  return match[2] ? `${formatDate(match[1])} ${match[2]}` : formatDate(match[1]);
}
