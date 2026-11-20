import { sessionOwner } from "@/lib/session";
import type {
  AnalysisResponse,
  AsyncStatus,
  CreateDocumentResponse,
  CreateResourceResponse,
  DocumentResponse,
  LearningPathResponse,
  MentoringFlow,
  ProfileResponse,
  ReviewResponse,
} from "./types";

const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/+$/, "");
const SESSION_KEY = "team07.session";
const FLOW_PREFIX = "team07.mentoringFlow";
const POLL_INTERVAL_MS = 2_000;
const POLL_TIMEOUT_MS = 120_000;

type Session = {
  username: string;
  accessToken: string;
  refreshToken: string;
  expiresAt: number;
};

type ErrorBody = {
  error?: { code?: string; message?: string; requestId?: string; retryable?: boolean };
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryable = false,
    readonly requestId?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function readSession(): Session | null {
  if (typeof window === "undefined") return null;
  try {
    const value = JSON.parse(window.localStorage.getItem(SESSION_KEY) ?? "null") as Partial<Session> | null;
    if (
      !value ||
      typeof value.username !== "string" ||
      typeof value.accessToken !== "string" ||
      typeof value.refreshToken !== "string" ||
      typeof value.expiresAt !== "number"
    ) {
      return null;
    }
    return value as Session;
  } catch {
    return null;
  }
}

async function apiError(response: Response): Promise<ApiError> {
  try {
    const body = (await response.json()) as ErrorBody;
    if (body.error?.code) {
      return new ApiError(
        response.status,
        body.error.code,
        body.error.message ?? "요청을 처리하지 못했어요.",
        body.error.retryable ?? response.status >= 500,
        body.error.requestId,
      );
    }
  } catch {
    // API Gateway의 본문 없는 401 등은 상태 코드로 처리한다.
  }
  if (response.status === 401) return new ApiError(401, "AUTH_REQUIRED", "로그인 후 다시 이용해 주세요.");
  return new ApiError(response.status, "HTTP_ERROR", "잠시 뒤 다시 시도해 주세요.", response.status >= 500);
}

async function refreshSession(session: Session): Promise<Session | null> {
  if (!session.refreshToken) return null;
  const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ refreshToken: session.refreshToken }),
  });
  if (!response.ok) return null;
  const tokens = (await response.json()) as { accessToken: string; refreshToken?: string; expiresIn: number };
  const next = {
    ...session,
    accessToken: tokens.accessToken,
    refreshToken: tokens.refreshToken ?? session.refreshToken,
    expiresAt: Date.now() + tokens.expiresIn * 1000,
  };
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(next));
  return next;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let session = readSession();
  if (!session) throw new ApiError(401, "AUTH_REQUIRED", "로그인 후 다시 이용해 주세요.");
  if (session.expiresAt - Date.now() < 60_000) session = (await refreshSession(session)) ?? session;

  const call = (accessToken: string) =>
    fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        ...(init.body ? { "content-type": "application/json" } : {}),
        ...init.headers,
        authorization: `Bearer ${accessToken}`,
      },
    });

  let response = await call(session.accessToken);
  if (response.status === 401) {
    const renewed = await refreshSession(session);
    if (!renewed) {
      window.localStorage.removeItem(SESSION_KEY);
      throw new ApiError(401, "AUTH_REQUIRED", "로그인이 만료됐어요. 다시 로그인해 주세요.");
    }
    response = await call(renewed.accessToken);
  }
  if (!response.ok) throw await apiError(response);
  return (await response.json()) as T;
}

function idempotencyKey(scope: string): string {
  return `${scope}-${crypto.randomUUID()}`;
}

async function post<T>(path: string, body?: unknown, scope = "mentoring"): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey(scope) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function statusOf(value: { status?: AsyncStatus; taskStatus?: AsyncStatus; extractionStatus?: string }): string {
  return value.status ?? value.taskStatus ?? value.extractionStatus ?? "PENDING";
}

export async function poll<T extends { status?: AsyncStatus; taskStatus?: AsyncStatus; extractionStatus?: string }>(
  load: () => Promise<T>,
  signal?: AbortSignal,
): Promise<T> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < POLL_TIMEOUT_MS) {
    if (signal?.aborted) throw new DOMException("요청이 취소됐어요.", "AbortError");
    const value = await load();
    const status = statusOf(value);
    if (["COMPLETED", "PARTIAL_SUCCESS", "REQUIRES_USER_REVIEW"].includes(status)) return value;
    if (status === "FAILED") throw new ApiError(500, "TASK_FAILED", "AI 처리를 완료하지 못했어요. 다시 시도해 주세요.", true);
    await new Promise<void>((resolve, reject) => {
      const onAbort = () => {
        window.clearTimeout(timer);
        reject(new DOMException("요청이 취소됐어요.", "AbortError"));
      };
      const timer = window.setTimeout(() => {
        signal?.removeEventListener("abort", onAbort);
        resolve();
      }, POLL_INTERVAL_MS);
      signal?.addEventListener("abort", onAbort, { once: true });
    });
  }
  throw new ApiError(408, "POLL_TIMEOUT", "처리가 계속 진행 중이에요. 잠시 뒤 결과 화면에서 다시 확인해 주세요.", true);
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.name === "AbortError") return "요청이 취소됐어요.";
  return "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요.";
}

export function createTextDocument(text: string): Promise<CreateDocumentResponse> {
  return post(
    "/api/v1/mentoring/documents/text",
    { text, documentType: "RESUME", title: "직무 진단 이력서" },
    "document-text",
  );
}

export async function createPdfDocument(file: File): Promise<CreateDocumentResponse> {
  const created = await post<{ documentId: string; uploadUrl: string }>(
    "/api/v1/mentoring/documents/upload-url",
    { fileName: file.name, contentType: "application/pdf", sizeBytes: file.size, documentType: "RESUME" },
    "document-upload",
  );
  const uploaded = await fetch(created.uploadUrl, { method: "PUT", headers: { "content-type": "application/pdf" }, body: file });
  if (!uploaded.ok) throw new ApiError(uploaded.status, "UPLOAD_FAILED", "PDF 업로드에 실패했어요. 다시 시도해 주세요.", true);
  return post(`/api/v1/mentoring/documents/${encodeURIComponent(created.documentId)}/complete`, undefined, "document-complete");
}

export function getDocument(documentId: string): Promise<DocumentResponse> {
  return request(`/api/v1/mentoring/documents/${encodeURIComponent(documentId)}`);
}

export function getProfile(): Promise<ProfileResponse> {
  return request("/api/v1/mentoring/profiles/me");
}

export function createAnalysis(profile: ProfileResponse, targetNcsCode: string): Promise<CreateResourceResponse> {
  return post(
    "/api/v1/mentoring/analyses",
    { profileId: profile.profileId, profileVersion: profile.profileVersion, targetNcsCode },
    "analysis",
  );
}

export function getAnalysis(analysisId: string): Promise<AnalysisResponse> {
  return request(`/api/v1/mentoring/analyses/${encodeURIComponent(analysisId)}`);
}

export function createReview(body: {
  inputText: string;
  documentType: string;
  analysisId: string;
  workspaceId?: string;
  questionText?: string;
  maxCharacters?: number;
}): Promise<CreateResourceResponse> {
  return post("/api/v1/mentoring/reviews", body, "review");
}

export function getReview(reviewId: string): Promise<ReviewResponse> {
  return request(`/api/v1/mentoring/reviews/${encodeURIComponent(reviewId)}`);
}

export function createLearningPath(body: {
  analysisId: string;
  weeklyStudyHours: number;
  preferredFormat: string;
  regionCode: string;
  targetDate?: string;
  workspaceId?: string;
}): Promise<CreateResourceResponse> {
  return post("/api/v1/mentoring/learning-paths", body, "learning-path");
}

export function getLearningPath(learningPathId: string): Promise<LearningPathResponse> {
  return request(`/api/v1/mentoring/learning-paths/${encodeURIComponent(learningPathId)}`);
}

function flowKey(): string | null {
  const session = readSession();
  return session ? `${FLOW_PREFIX}.${sessionOwner(session)}` : null;
}

export function readFlow(): MentoringFlow | null {
  const key = flowKey();
  if (!key) return null;
  try {
    const flow = JSON.parse(window.localStorage.getItem(key) ?? "null") as MentoringFlow | null;
    return flow?.analysisId && flow.profileId && flow.documentId ? flow : null;
  } catch {
    return null;
  }
}

export function saveFlow(flow: MentoringFlow): void {
  const key = flowKey();
  if (!key) throw new ApiError(401, "AUTH_REQUIRED", "로그인 후 다시 이용해 주세요.");
  window.localStorage.setItem(key, JSON.stringify(flow));
}

/** 진단·첨삭·학습 경로를 잇는 ID를 지운다 (개발 모드의 유저 정보 초기화). */
export function clearFlow(): void {
  const key = flowKey();
  if (key) window.localStorage.removeItem(key);
}

export function updateFlow(patch: Partial<MentoringFlow>): MentoringFlow | null {
  const current = readFlow();
  if (!current) return null;
  const next = { ...current, ...patch };
  saveFlow(next);
  return next;
}

export function safeExternalUrl(url?: string): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}
