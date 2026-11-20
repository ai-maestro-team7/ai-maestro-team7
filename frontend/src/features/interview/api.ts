import { apiGet, apiSend } from "@/lib/api";
import type { InterviewStatusBody, JobPostingText, StartInterviewInput, StartInterviewResponse } from "./types";

/**
 * 모의면접 API (`/api/v1/interview/*`, docs/개발계획서3.md §5).
 * 질문 생성·음성 변환·채점은 뒤에서 처리되므로 접수(202)만 받고 `/status`를 2초마다 조회한다.
 */
const BASE = "/api/v1/interview";

/** 세션을 만든다. 질문은 뒤에서 만들어지고 `/status`가 NEXT_QUESTION_READY가 되면 준비된 것이다. */
export function startInterview(input: StartInterviewInput): Promise<StartInterviewResponse> {
  return apiSend<StartInterviewResponse>("POST", `${BASE}/start`, input);
}

/** 채용공고 PDF에서 글자만 읽는다. 서버는 파일과 글을 저장하지 않는다 (#167). */
export function readJobPostingText(file: File): Promise<JobPostingText> {
  const form = new FormData();
  form.set("file", file, file.name);
  return apiSend<JobPostingText>("POST", `${BASE}/job-posting/text`, form);
}

export function getInterviewStatus(sessionId: string): Promise<InterviewStatusBody> {
  return apiGet<InterviewStatusBody>(`${BASE}/${encodeURIComponent(sessionId)}/status`);
}

type AnswerBase = { sessionId: string; answerId: string; timeLimitReached: boolean };

function answerForm({ sessionId, answerId, timeLimitReached }: AnswerBase): FormData {
  const form = new FormData();
  form.set("sessionId", sessionId);
  form.set("answerId", answerId);
  form.set("timeLimitReached", String(timeLimitReached));
  return form;
}

/** 녹음한 답변을 낸다. 같은 `answerId`를 두 번 내면 409 ANSWER_ALREADY_SUBMITTED. */
export function submitAudioAnswer(base: AnswerBase, audio: Blob): Promise<unknown> {
  const form = answerForm(base);
  // 파일 이름의 확장자는 쓰이지 않는다. 형식은 Blob의 type으로 정해진다 (webm, mp4 등)
  form.set("audio", audio, "answer");
  return apiSend("POST", `${BASE}/answer`, form);
}

/** 글로 쓴 답변을 낸다 (텍스트 방식). 음성 변환이 없어 전달력은 측정되지 않는다. */
export function submitTextAnswer(base: AnswerBase, text: string): Promise<unknown> {
  const form = answerForm(base);
  form.set("text", text);
  return apiSend("POST", `${BASE}/answer`, form);
}

export type FrameInput = {
  sessionId: string;
  type: "CALIBRATION" | "ANSWER";
  capturedAt: string;
  image: Blob;
  answerId?: string;
  questionId?: string;
};

/** 카메라 캡처 한 장을 보낸다. 서버는 시선·고개 각도만 저장하고 이미지는 저장하지 않는다. */
export function sendFrame(input: FrameInput): Promise<{ accepted: boolean; valid: boolean }> {
  const form = new FormData();
  form.set("sessionId", input.sessionId);
  form.set("type", input.type);
  form.set("capturedAt", input.capturedAt);
  if (input.answerId) form.set("answerId", input.answerId);
  if (input.questionId) form.set("questionId", input.questionId);
  form.set("image", input.image, "frame.jpg");
  return apiSend("POST", `${BASE}/frame`, form);
}
