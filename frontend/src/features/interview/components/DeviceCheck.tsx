"use client";

import { Check, Loader2, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { cn } from "@/lib/cn";
import { sendFrame } from "../api";
import { RULES } from "../data";
import { useInterviewStatus } from "../hooks/useInterviewStatus";
import { useMediaStream } from "../hooks/useMediaStream";
import { MIC_LEVEL_BARS, useMicLevel } from "../hooks/useMicLevel";
import { interviewQuery, parseMode, parseSessionId, readJob } from "../lib";
import { captureFrame, wait } from "../media";
import { CameraPreview } from "./CameraPreview";
import { MissingSession } from "./MissingSession";

type CheckState = "ok" | "wait" | "bad";
type Calibration = { state: "idle" | "running" | "done"; valid: number; sent: number };

/**
 * 모의면접 2단계: 장비 점검. 마이크·카메라 권한을 받고, 카메라 방식이면 정면 보정 캡처를 보낸다
 * (0.5초 간격 3초, `POST /interview/frame` CALIBRATION). 질문이 준비되면 면접을 시작할 수 있다.
 */
export function DeviceCheck() {
  const params = useSearchParams();
  const sessionId = parseSessionId(params.get("session"));
  const job = readJob(params.get("job"));
  const mode = parseMode(params.get("mode"));

  if (!sessionId) return <MissingSession />;
  return <DeviceCheckBody key={sessionId} sessionId={sessionId} job={job} mode={mode} />;
}

function DeviceCheckBody({ sessionId, job, mode }: { sessionId: string; job: string; mode: ReturnType<typeof parseMode> }) {
  const query = interviewQuery({ session: sessionId, job, mode });
  const needsMic = mode !== "text";
  const needsCamera = mode === "camera";

  const media = useMediaStream({ audio: needsMic, video: needsCamera });
  const levels = useMicLevel(media.stream, needsMic);
  const { status, error } = useInterviewStatus(sessionId);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [calibration, setCalibration] = useState<Calibration>({ state: "idle", valid: 0, sent: 0 });
  const running = useRef(false);

  const calibrate = useCallback(async () => {
    if (running.current) return;
    running.current = true;
    setCalibration({ state: "running", valid: 0, sent: 0 });
    const sends: Promise<boolean>[] = [];
    for (let i = 0; i < RULES.calibrationFrames; i += 1) {
      const image = await captureFrame(videoRef.current);
      if (image) {
        sends.push(
          sendFrame({ sessionId, type: "CALIBRATION", capturedAt: new Date().toISOString(), image }).then(
            (result) => result.valid,
            () => false,
          ),
        );
      }
      setCalibration((prev) => ({ ...prev, sent: i + 1 }));
      await wait(RULES.calibrationFrameMs);
    }
    const results = await Promise.all(sends);
    setCalibration({ state: "done", valid: results.filter(Boolean).length, sent: RULES.calibrationFrames });
    running.current = false;
  }, [sessionId]);

  // 카메라가 켜지면 잠깐 뒤에 한 번 자동으로 보정한다. 얼굴을 맞출 시간을 준다
  const cameraReady = needsCamera && media.status === "ready";
  useEffect(() => {
    if (!cameraReady) return;
    const timer = window.setTimeout(() => void calibrate(), 2000);
    return () => window.clearTimeout(timer);
  }, [cameraReady, calibrate]);

  const micHeard = levels.some((level) => level > 0.08);
  const questionReady = status?.stage === "NEXT_QUESTION_READY" && status.nextQuestion !== null;
  const failed = status?.status === "FAILED" || error !== null;

  const checks: { key: string; title: string; description: string; state: CheckState }[] = [];
  if (needsMic) {
    checks.push({
      key: "mic",
      title: "마이크",
      state: media.status === "ready" ? "ok" : media.status === "pending" ? "wait" : "bad",
      description:
        media.status === "ready"
          ? micHeard
            ? "소리가 잘 들어와요"
            : "마이크가 켜졌어요. 한마디 말해 보세요"
          : media.status === "pending"
            ? "권한을 확인하는 중이에요"
            : media.status === "unsupported"
              ? "이 브라우저에서는 마이크를 쓸 수 없어요"
              : "마이크 권한이 없어요. 주소창의 권한 설정에서 허용해 주세요",
    });
  }
  if (needsCamera) {
    const enough = calibration.valid >= RULES.calibrationMinValid;
    checks.push({
      key: "camera",
      title: "카메라 정면 보정",
      state:
        media.status !== "ready"
          ? media.status === "pending"
            ? "wait"
            : "bad"
          : calibration.state === "done"
            ? enough
              ? "ok"
              : "bad"
            : "wait",
      description:
        media.status !== "ready"
          ? media.status === "pending"
            ? "권한을 확인하는 중이에요"
            : "카메라를 쓸 수 없어요. 시선은 측정하지 않고 진행해요"
          : calibration.state === "done"
            ? enough
              ? "정면 기준을 잡았어요"
              : "얼굴을 충분히 찾지 못했어요. 다시 보정하지 않으면 시선은 측정하지 않아요"
            : calibration.state === "running"
              ? `정면을 3초 동안 봐 주세요 (${calibration.sent}/${RULES.calibrationFrames})`
              : "얼굴을 점선 안에 맞추면 곧 보정을 시작해요",
    });
  }
  checks.push({
    key: "questions",
    title: "질문",
    state: failed ? "bad" : questionReady ? "ok" : "wait",
    description: failed
      ? (status?.error?.message ?? error?.message ?? "질문을 만들지 못했어요.")
      : questionReady
        ? `${job} 질문 ${status?.progress.totalBaseQuestions ?? RULES.baseQuestions}개가 준비됐어요`
        : "자기소개서를 읽고 질문을 만드는 중이에요",
  });

  // 면접 시작: 질문이 준비됐고 마이크를 쓸 수 있을 때 (docs/개발계획서3.md §5.6). 보정이 도는 동안은 기다린다
  const micOk = !needsMic || media.status === "ready";
  const canStart = questionReady && micOk && calibration.state !== "running";

  return (
    <TwoColumn
      main={
        needsCamera ? (
          <div className="flex flex-col gap-3">
            <CameraPreview size="L" label="카메라 미리보기" stream={cameraReady ? media.stream : null} videoRef={videoRef} />
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-small text-grey-600">얼굴이 점선 안에 들어오게 맞춰 주세요. 영상은 저장하지 않아요.</p>
              {cameraReady && calibration.state === "done" && (
                <Button variant="line" size="M" onClick={() => void calibrate()}>
                  다시 보정
                </Button>
              )}
            </div>
          </div>
        ) : (
          <Panel tone="muted" className="flex flex-col gap-1 px-6 py-5">
            <p className="text-body font-bold text-grey-900">카메라 없이 진행해요</p>
            <p className="text-small text-grey-600">
              {mode === "voice" ? "답변 내용과 전달력만 확인해요." : "답변은 글로 적고 내용만 확인해요."}
            </p>
            {needsMic && media.status === "ready" && (
              <div aria-hidden className="mt-3 flex h-8 items-center gap-1">
                {[...Array<number>(Math.max(0, MIC_LEVEL_BARS - levels.length)).fill(0), ...levels].map((level, index) => (
                  <span
                    key={index}
                    className={cn("w-0.75 shrink-0 rounded-full", level > 0.04 ? "bg-blue-500" : "bg-grey-300")}
                    style={{ height: Math.max(4, Math.round(level * 30)) }}
                  />
                ))}
              </div>
            )}
          </Panel>
        )
      }
      rail={
        <div className="flex flex-col gap-6">
          <section aria-labelledby="device-status" className="flex flex-col gap-1">
            <h2 id="device-status" className="text-h3 font-bold text-grey-900">
              점검 상태
            </h2>
            <ul className="flex flex-col" aria-live="polite">
              {checks.map((check) => (
                <li key={check.key} className="flex gap-2.5 border-b border-grey-200 py-3 last:border-b-0">
                  <CheckIcon state={check.state} />
                  <div className="flex flex-col">
                    <p className="text-body font-bold text-grey-900">
                      {check.title}
                      <span className="sr-only">
                        {check.state === "ok" ? " 확인됨" : check.state === "wait" ? " 확인 중" : " 확인 필요"}
                      </span>
                    </p>
                    <p className="text-small text-grey-600">{check.description}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <div className="flex flex-col items-center gap-1.5">
            {canStart ? (
              <Button href={`/interview/session?${query}`} fullWidth>
                면접 시작
              </Button>
            ) : (
              <Button fullWidth disabled>
                {failed ? "면접을 시작할 수 없어요" : "준비 중"}
              </Button>
            )}
            {needsMic && (media.status === "denied" || media.status === "unsupported") && questionReady && (
              <Button href={`/interview/session?${interviewQuery({ session: sessionId, job, mode: "text" })}`} variant="line" fullWidth>
                글로 답하며 진행하기
              </Button>
            )}
            <Button href={`/interview?${interviewQuery({ job, mode })}`} variant="textMuted">
              설정으로 돌아가기
            </Button>
          </div>
        </div>
      }
    />
  );
}

function CheckIcon({ state }: { state: CheckState }) {
  if (state === "ok") return <Check aria-hidden className="mt-0.75 size-4.5 shrink-0 text-green-500" strokeWidth={2.5} />;
  if (state === "bad") return <X aria-hidden className="mt-0.75 size-4.5 shrink-0 text-red-500" strokeWidth={2.5} />;
  return <Loader2 aria-hidden className="mt-0.75 size-4.5 shrink-0 animate-spin text-grey-500" strokeWidth={2.5} />;
}
