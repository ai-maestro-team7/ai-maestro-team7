import { interviewDefaults, MODE_OPTIONS, TYPE_OPTIONS } from "./data";
import type { InterviewMode, InterviewStage, InterviewType, UnevaluableReason } from "./types";

const MODES: InterviewMode[] = ["camera", "voice", "text"];

/** URL 쿼리의 `mode` 값을 읽는다. 모르는 값이면 기본(음성 + 카메라). */
export function parseMode(value: string | null): InterviewMode {
  return MODES.includes(value as InterviewMode) ? (value as InterviewMode) : "camera";
}

export function modeLabel(mode: InterviewMode): string {
  return MODE_OPTIONS.find((option) => option.value === mode)?.label ?? "";
}

export function typeLabel(type: InterviewType | string | null | undefined): string {
  const found = TYPE_OPTIONS.find((option) => option.value === type)?.label;
  return found ? `${found} 면접` : "";
}

/** 세션 ID는 서버가 만든 UUID다. 형식이 다르면 없는 것으로 본다. */
export function parseSessionId(value: string | null): string | null {
  return value && /^[0-9a-f-]{36}$/.test(value) ? value : null;
}

/** 면접 단계 사이에 넘기는 값 (세션, 직무, 진행 방식)을 쿼리 문자열로 만든다. 자기소개서는 주소에 넣지 않는다. */
export function interviewQuery(values: { session?: string; job: string; mode: InterviewMode }): string {
  const params = new URLSearchParams({ job: values.job, mode: values.mode });
  if (values.session) params.set("session", values.session);
  return params.toString();
}

export function readJob(value: string | null): string {
  return value?.trim() || interviewDefaults.job;
}

/** 초 → `01:42` */
export function formatTimer(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** 답변을 낸 뒤 기다리는 동안 보여 주는 말 (docs/개발계획서3.md §5.6) */
export function stageMessage(stage: InterviewStage | undefined): string {
  switch (stage) {
    case "QUESTION_GENERATING":
      return "질문을 만드는 중";
    case "TRANSCRIBING":
      return "음성 변환 중";
    case "JUDGING":
      return "다음 질문 준비 중";
    case "REPORT_GENERATING":
    case "REPORT_READY":
      return "리포트 생성 중";
    default:
      return "처리 중";
  }
}

export function unevaluableMessage(reason: UnevaluableReason | null | undefined): string {
  if (reason === "TRANSCRIBE_FAILED") return "방금 답변은 음성을 글로 바꾸지 못했어요. 이 답변은 평가에서 빠져요.";
  return "방금 답변에서 말을 인식하지 못했어요. 이 답변은 평가에서 빠져요.";
}
