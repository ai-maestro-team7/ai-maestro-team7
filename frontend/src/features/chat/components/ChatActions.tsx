"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextArea } from "@/components/ui/TextArea";
import { ApiError, saveMyProfile } from "@/lib/api";
import type { BasicProfileInput } from "@/features/profile/types";
import { interviewHref, writeHandoff } from "../lib";
import type { ChatAction } from "../types";

type SaveAction = Extract<ChatAction, { type: "SAVE_CONDITIONS" }>;
type StartAction = Extract<ChatAction, { type: "START_INTERVIEW" }>;
type RequestAction = Extract<ChatAction, { type: "REQUEST_COVER_LETTER" }>;

/** 대화 조건 저장 묻기 (D-40). 누를 때만 기본 프로필에 쓴다. */
export function SaveConditions({ action }: { action: SaveAction }) {
  const [state, setState] = useState<"ask" | "saving" | "saved" | "skipped">("ask");
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setState("saving");
    setError(null);
    try {
      await saveMyProfile(action.profilePatch as BasicProfileInput);
      setState("saved");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "저장하지 못했어요. 다시 시도해 주세요.");
      setState("ask");
    }
  }

  if (state === "skipped") return <p className="text-small text-grey-600">이번 검색에만 썼어요. 프로필은 그대로예요.</p>;
  if (state === "saved") return <p className="text-small text-grey-800">내 프로필에 저장했어요. 다음 검색부터 이 조건을 써요.</p>;
  return (
    <div className="flex flex-col gap-2.5 rounded-field bg-grey-50 p-4">
      <p className="text-body font-bold text-grey-900">이 조건을 내 프로필에 저장할까요?</p>
      <p className="text-small text-grey-600">채팅으로 &quot;저장해 줘&quot;라고 답해도 돼요.</p>
      <p className="text-small text-grey-600">{action.conditions.join(" · ")}</p>
      {error && (
        <p role="alert" className="text-small text-red-500">
          {error}
        </p>
      )}
      <div className="flex gap-2">
        <Button size="M" onClick={save} disabled={state === "saving"}>
          저장하기
        </Button>
        <Button size="M" variant="line" onClick={() => setState("skipped")} disabled={state === "saving"}>
          이번만 쓰기
        </Button>
      </div>
    </div>
  );
}

/** 저장된 자기소개서로 모의면접 체험 시작 */
export function StartInterview({ action }: { action: StartAction }) {
  const router = useRouter();
  function start() {
    writeHandoff({ job: action.job, documentId: action.documentId, documentTitle: action.title, source: "chat" });
    router.push(interviewHref(action.job));
  }
  return (
    <div className="flex flex-col gap-2.5 rounded-field bg-grey-50 p-4">
      <p className="text-body font-bold text-grey-900">‘{action.job}’ 모의면접 체험</p>
      <p className="text-small text-grey-600">
        {action.title ?? "저장된 자기소개서"}로 질문을 만들어요. 체험용 면접이고 점수는 합격 확률이 아니에요.
      </p>
      <div>
        <Button size="M" onClick={start}>
          모의면접 시작하기
        </Button>
      </div>
    </div>
  );
}

/** 자기소개서가 없을 때: 채팅에서 받아 면접 화면으로 넘긴다. 자소서는 채팅 메시지로 보내지 않는다. */
export function CoverLetterForm({ action }: { action: RequestAction }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState<string>();
  const id = `cover-letter-${action.job}`;

  function start() {
    const trimmed = text.trim();
    if (trimmed.length < action.minChars || trimmed.length > action.maxChars) {
      setError(`자기소개서는 ${action.minChars.toLocaleString()}~${action.maxChars.toLocaleString()}자로 넣어 주세요.`);
      return;
    }
    writeHandoff({ job: action.job, coverLetter: trimmed, source: "chat" });
    router.push(interviewHref(action.job));
  }

  return (
    <div className="flex flex-col gap-2.5 rounded-field bg-grey-50 p-4">
      <p className="text-body font-bold text-grey-900">‘{action.job}’ 모의면접 체험에 쓸 자기소개서</p>
      <p className="text-small text-grey-600">
        면접 질문을 자기소개서에서 만들어요. 넣은 글은 이 채팅에 남기지 않고 면접 화면으로만 넘겨요.
      </p>
      <TextArea
        id={id}
        label="자기소개서"
        value={text}
        rows={6}
        maxLength={action.maxChars}
        onChange={(event) => setText(event.target.value)}
        error={error}
        placeholder="지원 동기, 경험, 배운 점을 붙여 넣어 주세요"
      />
      <div>
        <Button size="M" onClick={start} disabled={!text.trim()}>
          이 자소서로 면접 체험하기
        </Button>
      </div>
    </div>
  );
}
