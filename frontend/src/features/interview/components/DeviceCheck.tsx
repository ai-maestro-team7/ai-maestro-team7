"use client";

import { Check } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { TwoColumn } from "@/components/layout/PageContainer";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { deviceChecks, interviewDefaults, interviewQuestions } from "../data";
import { interviewQuery, parseMode, readJob } from "../lib";
import { CameraPreview } from "./CameraPreview";

/**
 * 모의면접 2단계: 장비 점검. 시연이라 카메라·마이크 권한을 요청하지 않고 점검 결과 예시를 보여준다.
 */
export function DeviceCheck() {
  const params = useSearchParams();
  const job = readJob(params.get("job"));
  const mode = parseMode(params.get("mode"));
  const query = interviewQuery({ job, mode });

  const checks = [
    ...(mode === "text" ? [] : [deviceChecks.mic]),
    ...(mode === "camera" ? [deviceChecks.camera] : []),
    {
      ...deviceChecks.questions,
      description: `${job} · ${interviewDefaults.interviewType} · ${interviewQuestions.length}개 준비됐어요`,
    },
  ];

  return (
    <TwoColumn
      main={
        mode === "camera" ? (
          <div className="flex flex-col gap-3">
            <CameraPreview size="L" label="카메라 미리보기 자리 (시연 화면)" />
            <p className="text-small text-grey-600">얼굴이 점선 안에 들어오게 맞춰 주세요 · 시연 화면</p>
          </div>
        ) : (
          <Panel tone="muted" className="flex flex-col gap-1 px-6 py-5">
            <p className="text-body font-bold text-grey-900">카메라 없이 진행해요</p>
            <p className="text-small text-grey-600">
              {mode === "voice" ? "답변 내용과 전달력만 확인해요." : "답변은 글로 적고 내용만 확인해요."}
            </p>
          </Panel>
        )
      }
      rail={
        <div className="flex flex-col gap-6">
          <section aria-labelledby="device-status" className="flex flex-col gap-1">
            <h2 id="device-status" className="text-h3 font-bold text-grey-900">
              점검 상태
            </h2>
            <ul className="flex flex-col">
              {checks.map((check) => (
                <li key={check.key} className="flex gap-2.5 border-b border-grey-200 py-3 last:border-b-0">
                  <Check aria-hidden className="mt-0.75 size-4.5 shrink-0 text-green-500" strokeWidth={2.5} />
                  <div className="flex flex-col">
                    <p className="text-body font-bold text-grey-900">
                      {check.title}
                      <span className="sr-only"> 확인됨</span>
                    </p>
                    <p className="text-small text-grey-600">{check.description}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <div className="flex flex-col items-center gap-1.5">
            <Button href={`/interview/session?${query}`} fullWidth>
              면접 시작
            </Button>
            <Button href={`/interview?${query}`} variant="textMuted">
              설정으로 돌아가기
            </Button>
          </div>
        </div>
      }
    />
  );
}
