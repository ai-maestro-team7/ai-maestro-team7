"use client";

import { useRouter } from "next/navigation";
import { useEffect, useEffectEvent, useState } from "react";
import { Button } from "@/components/ui/Button";
import { DotList } from "@/components/ui/DetailSection";
import { Dialog } from "@/components/ui/Dialog";
import { forgetSavedIds } from "@/features/jobs/saved";
import { clearConversations } from "@/features/mentor/conversations";
import { clearFlow } from "@/features/mentoring/api";
import { ApiError, type ResetCounts, resetMyData } from "@/lib/api";

const DELETED_ITEMS = [
  "프로필",
  "저장한 공고·알림",
  "이력서·진단·첨삭·학습 경로",
  "모의면접 기록",
  "이 브라우저의 대화 기록",
];

/** 초기화 결과를 보여준 뒤 기본 정보 입력으로 넘어가기까지 기다리는 시간 */
const REDIRECT_DELAY_MS = 2500;

type Phase =
  | { step: "confirm"; error?: { message: string; requestId?: string } }
  | { step: "pending" }
  /** 서버 초기화까지 끝남. `deleted`는 서버가 지운 수 */
  | { step: "done"; deleted?: ResetCounts }
  /** 초기화 API가 아직 배포되지 않음 (404·501) */
  | { step: "unavailable" }
  | { step: "localDone" };

/**
 * 이 브라우저에 사용자별로 둔 값을 지운다: AI 멘토 대화(`team07.mentorChats.<sub>`)와
 * 진단·첨삭·학습 경로를 잇는 ID(`team07.mentoringFlow.<sub>`). 로그인 세션과 개발 모드 표시는 남긴다.
 */
function clearLocalUserData(): void {
  clearConversations();
  clearFlow();
}

/**
 * 개발 모드의 "유저 정보 모두 초기화". 지울 것을 먼저 알리고 `POST /api/v1/me/reset`을 부른다.
 * 끝나면 이 브라우저의 기록도 지우고, 처음 들어온 사용자가 가는 기본 정보 입력(`/profile/`)으로 보낸다.
 */
export function ResetDataDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const [phase, setPhase] = useState<Phase>({ step: "confirm" });

  function goToProfile() {
    onClose();
    router.replace("/profile/");
  }

  const goToProfileLater = useEffectEvent(goToProfile);
  useEffect(() => {
    if (phase.step !== "done") return;
    const timer = window.setTimeout(() => goToProfileLater(), REDIRECT_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [phase.step]);

  async function reset() {
    setPhase({ step: "pending" });
    try {
      const { deleted } = await resetMyData();
      clearLocalUserData();
      // 서버의 저장 목록이 비었으니 화면이 읽어 둔 저장 표시도 버린다
      forgetSavedIds();
      setPhase({ step: "done", deleted });
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 501)) {
        setPhase({ step: "unavailable" });
        return;
      }
      setPhase({
        step: "confirm",
        error:
          e instanceof ApiError
            ? { message: e.message, requestId: e.requestId }
            : { message: "서버에 연결하지 못했어요. 잠시 뒤 다시 시도해 주세요." },
      });
    }
  }

  function resetLocalOnly() {
    clearLocalUserData();
    setPhase({ step: "localDone" });
  }

  if (phase.step === "done") {
    return (
      <Dialog
        title="모두 초기화했어요"
        onClose={goToProfile}
        actions={
          <Button size="M" onClick={goToProfile}>
            기본 정보 입력하기
          </Button>
        }
      >
        <p>
          {phase.deleted
            ? `서버에서 기록 ${phase.deleted.items}건, 파일 ${phase.deleted.files}개, 알림 일정 ${phase.deleted.schedules}건을 지웠어요.`
            : "서버에 저장된 정보를 지웠어요."}{" "}
          이 브라우저의 대화 기록도 지웠어요.
        </p>
        <p>곧 기본 정보 입력으로 이동해요.</p>
      </Dialog>
    );
  }

  if (phase.step === "unavailable") {
    return (
      <Dialog
        title="서버 정보는 아직 초기화할 수 없어요"
        onClose={onClose}
        actions={
          <>
            <Button variant="line" size="M" onClick={onClose}>
              닫기
            </Button>
            <Button size="M" onClick={resetLocalOnly}>
              이 브라우저 기록만 지우기
            </Button>
          </>
        }
      >
        <p>초기화 API(POST /api/v1/me/reset)가 아직 배포되지 않아 서버에 저장된 정보는 지우지 못했어요.</p>
        <p>이 브라우저에 있는 대화 기록과 진단·첨삭·학습 경로 연결 정보만 지울 수 있어요.</p>
      </Dialog>
    );
  }

  if (phase.step === "localDone") {
    return (
      <Dialog
        title="이 브라우저 기록을 지웠어요"
        onClose={onClose}
        actions={
          <Button size="M" onClick={onClose}>
            닫기
          </Button>
        }
      >
        <p>서버에 저장된 정보는 그대로예요.</p>
      </Dialog>
    );
  }

  const pending = phase.step === "pending";
  const error = phase.step === "confirm" ? phase.error : undefined;

  return (
    <Dialog
      title="유저 정보를 모두 초기화할까요?"
      onClose={onClose}
      locked={pending}
      actions={
        <>
          <Button variant="line" size="M" onClick={onClose} disabled={pending}>
            취소
          </Button>
          <Button size="M" onClick={reset} disabled={pending}>
            {pending ? "초기화하는 중" : "모두 초기화"}
          </Button>
        </>
      }
    >
      <p>이 계정의 아래 정보를 모두 지워요.</p>
      <DotList items={DELETED_ITEMS} />
      <p>지운 정보는 되돌릴 수 없어요. 로그인은 그대로 유지돼요.</p>
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error.message}
          {error.requestId && ` (요청 번호 ${error.requestId})`}
        </p>
      )}
    </Dialog>
  );
}
