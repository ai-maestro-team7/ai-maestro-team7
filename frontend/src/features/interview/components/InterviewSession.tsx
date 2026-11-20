"use client";

import { useRouter, useSearchParams } from "next/navigation";
import {
  createContext,
  type ReactNode,
  type RefObject,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { TextArea } from "@/components/ui/TextArea";
import { ApiError } from "@/lib/api";
import { sendFrame, submitAudioAnswer, submitTextAnswer } from "../api";
import { answerGuide, RULES } from "../data";
import { useInterviewStatus } from "../hooks/useInterviewStatus";
import { useMediaStream } from "../hooks/useMediaStream";
import { useMicLevel } from "../hooks/useMicLevel";
import { interviewQuery, modeLabel, parseMode, parseSessionId, readJob, stageMessage, unevaluableMessage } from "../lib";
import { type AnswerRecorder, canRecord, captureFrame, startAnswerRecorder, wait } from "../media";
import type { InterviewMode, NextQuestion } from "../types";
import { CameraPreview } from "./CameraPreview";
import { InterviewHeader } from "./InterviewHeader";
import { MissingSession } from "./MissingSession";
import { Recorder } from "./Recorder";

/**
 * 모의면접 3단계: 면접. 질문은 서버가 하나씩 준다 (`/status` 2초 조회).
 * 질문 음성 재생 → 녹음(최대 2분)과 2초 간격 캡처 → 답변 제출 → 꼬리질문 또는 다음 질문 → 리포트.
 * 순서와 꼬리질문 여부는 서버가 정하고, 화면은 받은 질문에 답을 보내기만 한다.
 *
 * 배치: 가운데 큰 카메라 영상, 그 위에 질문 카드, 아래에 답변 카드. 녹음 중에는 스페이스바로 답변을 마친다.
 */
export function InterviewSession() {
  const params = useSearchParams();
  const sessionId = parseSessionId(params.get("session"));
  const job = readJob(params.get("job"));
  const mode = parseMode(params.get("mode"));

  if (!sessionId) {
    return (
      <>
        <InterviewHeader title="AI 모의면접" step={3} />
        <MissingSession />
      </>
    );
  }
  return <ActiveSession key={sessionId} sessionId={sessionId} job={job} requestedMode={mode} />;
}

/**
 * 영상 위·아래 자리. 질문·답변 카드는 상태마다 다른 컴포넌트가 그리지만, 카메라 영상은 한자리에 계속 둬야
 * 질문이 바뀔 때 영상이 다시 붙지 않는다. 그래서 카드는 포털로 이 두 자리에 넣는다.
 */
const SlotContext = createContext<{ top: HTMLElement | null; bottom: HTMLElement | null }>({ top: null, bottom: null });

function AboveStage({ children }: { children: ReactNode }) {
  const { top } = useContext(SlotContext);
  return top ? createPortal(children, top) : null;
}

function BelowStage({ children }: { children: ReactNode }) {
  const { bottom } = useContext(SlotContext);
  return bottom ? createPortal(children, bottom) : null;
}

function ActiveSession({ sessionId, job, requestedMode }: { sessionId: string; job: string; requestedMode: InterviewMode }) {
  const router = useRouter();
  // 마이크를 쓸 수 없으면 글로 답하게 바꿀 수 있다
  const [typing, setTyping] = useState(false);
  const mode: InterviewMode = typing ? "text" : requestedMode;
  const needsMic = mode !== "text";
  const needsCamera = mode === "camera";

  const media = useMediaStream({ audio: needsMic, video: needsCamera });
  const { status, error } = useInterviewStatus(sessionId);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  // 이미 답을 보낸 answerId. 서버 상태가 바뀌기 전에 같은 질문이 다시 뜨지 않게 한다
  const [submitted, setSubmitted] = useState<ReadonlySet<string>>(new Set());

  const completed = status?.status === "COMPLETED";
  useEffect(() => {
    if (completed) router.replace(`/interview/report?${interviewQuery({ session: sessionId, job, mode: requestedMode })}`);
  }, [completed, router, sessionId, job, requestedMode]);

  const onSubmitted = useCallback((answerId: string) => setSubmitted((prev) => new Set(prev).add(answerId)), []);

  const question =
    status?.stage === "NEXT_QUESTION_READY" && status.nextQuestion && !submitted.has(status.nextQuestion.answerId)
      ? status.nextQuestion
      : null;
  const total = status?.progress.totalBaseQuestions ?? RULES.baseQuestions;
  const number = status?.progress.baseQuestionNo ?? 1;
  const progressLabel = `질문 ${number} / ${total}${question?.isFollowUp ? " · 추가 질문" : ""}`;
  const failed = status?.status === "FAILED" || error !== null;
  const micBlocked = needsMic && (media.status === "denied" || media.status === "unsupported" || (media.status === "ready" && !canRecord()));
  const lastAnswer = status?.lastAnswer;

  const [top, setTop] = useState<HTMLDivElement | null>(null);
  const [bottom, setBottom] = useState<HTMLDivElement | null>(null);

  let content: ReactNode;
  if (failed) {
    content = (
      <AboveStage>
        <Notice
          title={status?.error?.message ?? error?.message ?? "면접을 이어 갈 수 없어요."}
          description="처음부터 다시 시작해 주세요."
          action={
            <Button href={`/interview?${interviewQuery({ job, mode: requestedMode })}`} size="M">
              면접 설정으로
            </Button>
          }
        />
      </AboveStage>
    );
  } else if (question && micBlocked) {
    content = (
      <>
        <AboveStage>
          <QuestionCard question={question} />
        </AboveStage>
        <BelowStage>
          <Notice
            title="마이크를 쓸 수 없어요"
            description="브라우저에서 마이크 권한을 허용한 뒤 새로고침하거나, 글로 답할 수 있어요."
            action={
              <Button size="M" onClick={() => setTyping(true)}>
                글로 답하기
              </Button>
            }
          />
        </BelowStage>
      </>
    );
  } else if (question && needsMic && media.status !== "ready") {
    content = (
      <AboveStage>
        <Waiting label="마이크를 준비하는 중" />
      </AboveStage>
    );
  } else if (question) {
    content = (
      <>
        {lastAnswer && !lastAnswer.evaluable && (
          <AboveStage>
            <p role="status" className="text-small text-grey-600">
              {unevaluableMessage(lastAnswer.reason)}
            </p>
          </AboveStage>
        )}
        <QuestionRound
          key={question.answerId}
          sessionId={sessionId}
          question={question}
          mode={mode}
          stream={media.stream}
          videoRef={videoRef}
          onSubmitted={onSubmitted}
        />
      </>
    );
  } else {
    content = (
      <AboveStage>
        <Waiting label={completed ? "리포트로 이동하는 중" : stageMessage(status?.stage)} />
      </AboveStage>
    );
  }

  return (
    <>
      <InterviewHeader title="AI 모의면접" step={3} description={`${job} · ${modeLabel(mode)}`} />
      <div className="mx-auto flex w-full max-w-main flex-col gap-5">
        <ProgressBar label={progressLabel} value={Math.min(number, total) / total} />
        {/* 질문 카드 자리 → 카메라 영상 → 답변 카드 자리. 빈 자리는 숨겨 간격이 생기지 않게 한다 */}
        <div ref={setTop} className="flex flex-col gap-3 empty:hidden" />
        <SessionStage
          mode={mode}
          stream={needsCamera && media.status === "ready" ? media.stream : null}
          videoRef={videoRef}
          cameraFailed={needsCamera && media.status !== "ready" && media.status !== "pending"}
        />
        <div ref={setBottom} className="flex flex-col gap-3 empty:hidden" />
        {mode === "text" && <AnswerGuide />}
        <div>
          <Button href={`/interview?${interviewQuery({ job, mode: requestedMode })}`} variant="textMuted">
            면접 종료
          </Button>
        </div>
      </div>
      <SlotContext value={{ top, bottom }}>{content}</SlotContext>
    </>
  );
}

/** 영상 위 질문 카드. 질문 음성을 읽는 중이면 그 안내와 [바로 답변 시작]을 아래에 붙인다. */
function QuestionCard({ question, footer }: { question: NextQuestion; footer?: ReactNode }) {
  return (
    <Panel as="section" aria-labelledby="interview-question" aria-live="polite" className="flex flex-col gap-2.5 p-5">
      <p className="text-small font-bold text-grey-600">AI 면접관{question.isFollowUp ? " · 추가 질문" : ""}</p>
      <h2 id="interview-question" className="text-h2 font-bold text-grey-900">
        {question.text}
      </h2>
      {footer}
    </Panel>
  );
}

function Waiting({ label }: { label: string }) {
  return (
    <div role="status" className="flex flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-14 text-center">
      <span aria-hidden className="size-6 animate-spin rounded-full border-2 border-grey-300 border-t-blue-500" />
      <p className="text-body font-bold text-grey-900">{label}</p>
      <p className="text-small text-grey-600">잠시만 기다려 주세요. 화면을 닫지 않아도 돼요.</p>
    </div>
  );
}

function Notice({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-3 border-t border-b border-t-grey-800 border-b-grey-200 py-12 text-center">
      <p className="text-body font-bold text-grey-900">{title}</p>
      <p className="text-small text-grey-600">{description}</p>
      {action}
    </div>
  );
}

type RoundPhase = "listening" | "idle" | "recording" | "sending" | "error";

type RoundProps = {
  sessionId: string;
  question: NextQuestion;
  mode: InterviewMode;
  stream: MediaStream | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  onSubmitted: (answerId: string) => void;
};

/** 질문 하나에 답하는 한 번. 질문이 바뀌면 `key`로 다시 만든다. */
function QuestionRound(props: RoundProps) {
  return props.mode === "text" ? <TextRound {...props} /> : <VoiceRound {...props} />;
}

function submitFailure(error: unknown): string {
  if (error instanceof ApiError && error.status === 413) return "녹음 파일이 너무 커요. 조금 짧게 다시 답해 주세요.";
  if (error instanceof ApiError && error.status === 400) return error.message;
  return "답변을 보내지 못했어요. 다시 시도해 주세요.";
}

/** 이미 받은 답변이면(중복 제출, 다른 탭에서 진행) 보낸 것으로 본다 */
function alreadyAccepted(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409;
}

function VoiceRound({ sessionId, question, mode, stream, videoRef, onSubmitted }: RoundProps) {
  // 음성 주소는 처음 받은 것을 그대로 쓴다. 서버는 `/status`를 줄 때마다 임시 주소를 새로 발급하므로,
  // 그때마다 바꾸면 2초마다 음성이 처음부터 다시 재생된다
  const [audioUrl] = useState(question.audioUrl);
  // 질문 음성이 있으면 먼저 들려주고, 끝나면 녹음을 시작한다. 없으면 [답변 시작]을 누를 때 시작한다
  const [phase, setPhase] = useState<RoundPhase>(audioUrl ? "listening" : "idle");
  const [elapsed, setElapsed] = useState(0);
  const [failure, setFailure] = useState<string>();
  const levels = useMicLevel(stream, phase === "recording");

  const recorder = useRef<AnswerRecorder | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const recorded = useRef<{ blob: Blob; timeLimitReached: boolean } | null>(null);
  const frames = useRef(new Set<Promise<unknown>>());
  const frameTimer = useRef<number | undefined>(undefined);
  const clock = useRef<number | undefined>(undefined);
  const finishing = useRef(false);

  const stopTimers = useCallback(() => {
    window.clearInterval(frameTimer.current);
    window.clearInterval(clock.current);
  }, []);

  const send = useCallback(async () => {
    const answer = recorded.current;
    if (!answer) return;
    setPhase("sending");
    setFailure(undefined);
    try {
      await submitAudioAnswer({ sessionId, answerId: question.answerId, timeLimitReached: answer.timeLimitReached }, answer.blob);
      onSubmitted(question.answerId);
    } catch (e) {
      if (alreadyAccepted(e)) {
        onSubmitted(question.answerId);
        return;
      }
      setFailure(submitFailure(e));
      setPhase("error");
    }
  }, [sessionId, question.answerId, onSubmitted]);

  /** 답변 완료: 캡처 중단 → 보내던 이미지를 최대 3초 기다림 → 녹음 파일 제출 (docs/개발계획서3.md §5.6) */
  const finish = useCallback(
    async (timeLimitReached: boolean) => {
      if (finishing.current || !recorder.current) return;
      finishing.current = true;
      setPhase("sending");
      stopTimers();
      const blob = await recorder.current.stop();
      await Promise.race([Promise.allSettled([...frames.current]), wait(RULES.frameFlushMs)]);
      recorded.current = { blob, timeLimitReached };
      await send();
    },
    [send, stopTimers],
  );

  const begin = useCallback(() => {
    if (recorder.current || !stream) return;
    audio.current?.pause();
    recorder.current = startAnswerRecorder(stream);
    setPhase("recording");
    const startedAt = Date.now();
    clock.current = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAt) / 1000);
      setElapsed(seconds);
      if (seconds >= RULES.answerLimitSec) void finish(true); // 2분이 되면 자동 제출
    }, 250);
    if (mode === "camera") {
      const capture = async () => {
        const image = await captureFrame(videoRef.current);
        if (!image || finishing.current) return;
        const sending = sendFrame({
          sessionId,
          type: "ANSWER",
          capturedAt: new Date().toISOString(),
          image,
          answerId: question.answerId,
          questionId: question.questionId,
        }).catch(() => undefined); // 캡처 한 장이 실패해도 면접은 계속한다
        frames.current.add(sending);
        void sending.finally(() => frames.current.delete(sending));
      };
      void capture();
      frameTimer.current = window.setInterval(() => void capture(), RULES.answerFrameMs);
    }
  }, [stream, mode, videoRef, sessionId, question.answerId, question.questionId, finish]);

  // 질문 음성 재생. 자동 재생이 막히면 [답변 시작] 버튼으로 넘어간다
  useEffect(() => {
    if (!audioUrl) return;
    const player = new Audio(audioUrl);
    audio.current = player;
    player.onended = () => begin();
    player.onerror = () => setPhase((prev) => (prev === "listening" ? "idle" : prev));
    player.play().catch(() => setPhase((prev) => (prev === "listening" ? "idle" : prev)));
    return () => {
      player.onended = null;
      player.onerror = null;
      player.pause();
    };
    // 질문마다 한 번만 재생한다. begin은 스트림이 바뀔 때 새로 만들어지므로 넣지 않는다
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl]);

  // 화면을 떠나면 녹음과 캡처를 멈춘다
  useEffect(
    () => () => {
      stopTimers();
      if (!finishing.current) recorder.current?.cancel();
    },
    [stopTimers],
  );

  // 녹음 중에는 스페이스바로 답변을 마친다. 글을 쓰거나 다른 버튼·링크에 초점이 있으면 그 동작을 그대로 둔다
  useEffect(() => {
    if (phase !== "recording") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, button, a, [contenteditable='true']")) return;
      event.preventDefault(); // 화면이 아래로 내려가지 않게 한다
      void finish(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, finish]);

  const remaining = RULES.answerLimitSec - elapsed;
  // 30초, 10초 전부터 남은 시간을 알린다
  const notice =
    phase === "recording" && remaining <= Math.max(...RULES.warnAtSec) ? `${Math.max(remaining, 0)}초 남았어요` : undefined;

  return (
    <>
      <AboveStage>
        <QuestionCard
          question={question}
          footer={
            phase === "listening" && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-grey-200 pt-3.5">
                <p className="text-small text-grey-600">질문을 읽어 드리고 있어요. 끝나면 녹음을 시작해요.</p>
                <Button variant="line" size="M" onClick={begin}>
                  바로 답변 시작
                </Button>
              </div>
            )
          }
        />
      </AboveStage>
      <BelowStage>
        <Panel className="flex flex-col gap-4 p-5">
          {phase === "listening" || phase === "idle" ? (
            <p className="text-body text-grey-900">
              {phase === "idle"
                ? `준비되면 답변을 시작해 주세요. ${RULES.answerLimitSec / 60}분까지 답할 수 있어요.`
                : "질문이 끝나면 바로 녹음이 시작돼요."}
            </p>
          ) : (
            <Recorder elapsed={Math.min(elapsed, RULES.answerLimitSec)} limit={RULES.answerLimitSec} levels={levels} notice={notice} />
          )}
          {failure && (
            <p role="alert" className="text-small text-red-500">
              {failure}
            </p>
          )}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-grey-200 pt-4">
            <p className="text-small text-grey-600">
              {phase === "recording" ? (
                <>
                  <kbd className="rounded-check border border-grey-300 bg-grey-50 px-1.5 py-0.5 font-sans text-small text-grey-800">
                    스페이스바
                  </kbd>
                  를 눌러도 답변을 마칠 수 있어요
                </>
              ) : phase === "sending" ? (
                "답변을 보내고 있어요"
              ) : (
                "녹음 중에는 스페이스바로도 답변을 마칠 수 있어요"
              )}
            </p>
            {phase === "error" ? (
              <Button onClick={() => void send()}>다시 보내기</Button>
            ) : phase === "idle" ? (
              <Button onClick={begin}>답변 시작</Button>
            ) : (
              <Button onClick={() => void finish(false)} disabled={phase !== "recording"}>
                {phase === "sending" ? "답변 보내는 중" : "답변 완료"}
              </Button>
            )}
          </div>
        </Panel>
      </BelowStage>
    </>
  );
}

function TextRound({ sessionId, question, onSubmitted }: RoundProps) {
  const [answer, setAnswer] = useState("");
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState<string>();
  const tooLong = answer.length > RULES.answerTextMax;

  async function handleSubmit() {
    setPending(true);
    setFailure(undefined);
    try {
      await submitTextAnswer({ sessionId, answerId: question.answerId, timeLimitReached: false }, answer);
      onSubmitted(question.answerId);
    } catch (e) {
      if (alreadyAccepted(e)) {
        onSubmitted(question.answerId);
        return;
      }
      setFailure(submitFailure(e));
      setPending(false);
    }
  }

  return (
    <>
      <AboveStage>
        <QuestionCard question={question} />
      </AboveStage>
      <BelowStage>
        <Panel className="flex flex-col gap-4 p-5">
          <TextArea
            id={`answer-${question.answerId}`}
            label="내 답변"
            rows={6}
            value={answer}
            onChange={(event) => setAnswer(event.target.value)}
            counterSuffix={`/ ${RULES.answerTextMax.toLocaleString()}자`}
            error={tooLong ? `답변은 ${RULES.answerTextMax.toLocaleString()}자까지 쓸 수 있어요.` : failure}
            disabled={pending}
          />
          <div className="flex justify-end">
            <Button onClick={() => void handleSubmit()} disabled={pending || tooLong || answer.trim().length === 0}>
              {pending ? "답변 보내는 중" : "답변 완료"}
            </Button>
          </div>
        </Panel>
      </BelowStage>
    </>
  );
}

/** 글로 답할 때 답변 카드 아래에 두는 가이드 */
function AnswerGuide() {
  return (
    <aside aria-labelledby="answer-guide" className="flex flex-col gap-3">
      <h2 id="answer-guide" className="text-h3 font-bold text-grey-900">
        답변 가이드
      </h2>
      <ol className="flex flex-col">
        {answerGuide.map((item, i) => (
          <li key={item.title} className="flex gap-2.5 border-b border-grey-200 py-3 last:border-b-0">
            <span className="text-body font-bold text-grey-500">{i + 1}</span>
            <span className="flex flex-col gap-0.5">
              <span className="text-body font-bold text-grey-900">{item.title}</span>
              <span className="text-small text-grey-600">{item.description}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="text-small text-grey-600">글로 답하면 답변 내용만 평가해요.</p>
    </aside>
  );
}

/**
 * 질문 카드와 답변 카드 사이. 카메라 방식이면 큰 영상(장비 점검과 같은 700×440 비율),
 * 음성만이면 카메라 없이 진행한다는 안내, 텍스트면 아무것도 두지 않는다.
 */
function SessionStage({
  mode,
  stream,
  videoRef,
  cameraFailed,
}: {
  mode: InterviewMode;
  stream: MediaStream | null;
  videoRef: RefObject<HTMLVideoElement | null>;
  cameraFailed: boolean;
}) {
  if (mode === "text") return null;

  if (mode === "voice") {
    return (
      <Panel tone="muted" className="flex flex-col gap-1 p-5">
        <p className="text-body font-bold text-grey-900">카메라 없이 진행 중이에요</p>
        <p className="text-small text-grey-600">답변 내용과 전달력만 확인해요. 녹음은 글로 바꾼 뒤 바로 지워요.</p>
      </Panel>
    );
  }

  return (
    <section aria-label="카메라" className="flex flex-col gap-2">
      <CameraPreview size="L" label="카메라 미리보기" stream={stream} videoRef={videoRef} />
      <p className="text-small text-grey-600">
        <span className="font-medium text-grey-900">
          {cameraFailed ? "카메라를 쓸 수 없어 시선은 측정하지 않아요." : "답변하는 동안 2초마다 시선을 확인해요."}
        </span>{" "}
        시선과 고개 방향만 기록하고 얼굴 이미지는 저장하지 않아요.
      </p>
    </section>
  );
}
