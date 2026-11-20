import { interviewDefaults, MODE_OPTIONS } from "./data";
import type { InterviewMode } from "./types";

const MODES: InterviewMode[] = ["camera", "voice", "text"];

/** URL 쿼리의 `mode` 값을 읽는다. 모르는 값이면 기본(음성 + 카메라). */
export function parseMode(value: string | null): InterviewMode {
  return MODES.includes(value as InterviewMode) ? (value as InterviewMode) : "camera";
}

export function modeLabel(mode: InterviewMode): string {
  return MODE_OPTIONS.find((option) => option.value === mode)?.label ?? "";
}

/** 면접 단계 사이에 넘기는 값 (직무, 진행 방식)을 쿼리 문자열로 만든다. */
export function interviewQuery({ job, mode }: { job: string; mode: InterviewMode }): string {
  return new URLSearchParams({ job, mode }).toString();
}

export function readJob(value: string | null): string {
  return value?.trim() || interviewDefaults.job;
}

/** 초 → `01:42` */
export function formatTimer(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}
