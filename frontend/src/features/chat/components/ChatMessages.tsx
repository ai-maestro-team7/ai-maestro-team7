"use client";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/Chip";
import { asOfLabel } from "../lib";
import type { ChatMessage } from "../types";
import { CoverLetterForm, SaveConditions, StartInterview } from "./ChatActions";
import { PolicyCard, PostingCard } from "./ChatCards";

/** 조회만 실패한 답. 다시 보내지 않고 같은 답을 다시 확인한다 */
export const POLL_FAILED = "POLL_FAILED";

export function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <p className="max-w-[85%] self-end whitespace-pre-wrap rounded-card bg-grey-100 px-3.5 py-2.5 text-body text-grey-900">
      <span className="sr-only">내 말: </span>
      {message.content}
      {message.attachments?.length ? <span className="block text-small text-grey-600">서류 첨부</span> : null}
    </p>
  );
}

/**
 * Agent 답 하나. 카드·버튼은 서버가 도구 결과로 만든 것만 그린다.
 * `latest`인 답에만 이어서 묻기 칩과 다시 보내기 버튼을 둔다.
 */
export function AssistantMessage({
  message,
  latest,
  busy,
  onAsk,
  onRetry,
}: {
  message: ChatMessage;
  latest: boolean;
  busy: boolean;
  onAsk: (text: string) => void;
  onRetry: () => void;
}) {
  if (message.status === "PENDING" || message.status === "PROCESSING") {
    return (
      <p role="status" className="text-body text-grey-600">
        AI 멘토가 공고와 정책을 찾고 있어요…
      </p>
    );
  }
  if (message.status === "CANCELLED") {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-body text-grey-600">답변을 멈췄어요.</p>
        {latest && (
          <Button size="M" variant="line" onClick={onRetry} disabled={busy}>
            다시 보내기
          </Button>
        )}
      </div>
    );
  }
  if (message.status === "FAILED") {
    return (
      <div role="alert" className="flex flex-col items-start gap-2">
        <p className="text-body text-grey-900">{message.error?.message ?? "답을 만들지 못했어요."}</p>
        {latest && (message.error?.retryable ?? true) && (
          <Button size="M" variant="line" onClick={onRetry} disabled={busy}>
            {message.error?.code === POLL_FAILED ? "다시 확인하기" : "다시 보내기"}
          </Button>
        )}
      </div>
    );
  }
  const postings = (message.cards ?? []).flatMap((c) => (c.type === "POSTING" ? [c.posting] : []));
  const policies = (message.cards ?? []).flatMap((c) => (c.type === "POLICY" ? [c.policy] : []));
  const footnote = [message.notice, asOfLabel(message.dataAsOf)].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col gap-3">
      <p className="text-small font-bold text-grey-600">AI 멘토</p>
      <p className="whitespace-pre-wrap text-body text-grey-900">{message.reply}</p>
      {postings.length > 0 && (
        <section aria-label="찾은 채용공고" className="flex flex-col gap-2">
          <p className="text-small font-bold text-grey-800">채용공고 {postings.length}개</p>
          <ul className="grid gap-2 md:grid-cols-2">
            {postings.map((posting) => (
              <PostingCard key={posting.jobPostingId} posting={posting} />
            ))}
          </ul>
        </section>
      )}
      {policies.length > 0 && (
        <section aria-label="받을 수 있는 청년정책" className="flex flex-col gap-2">
          <p className="text-small font-bold text-grey-800">청년정책 {policies.length}개</p>
          <ul className="grid gap-2 md:grid-cols-2">
            {policies.map((policy) => (
              <PolicyCard key={policy.policyId} policy={policy} />
            ))}
          </ul>
        </section>
      )}
      {footnote && <p className="text-small text-grey-500">{footnote}</p>}
      {(message.actions ?? []).map((action, index) => {
        const key = `${action.type}-${index}`;
        if (action.type === "SAVE_CONDITIONS") return <SaveConditions key={key} action={action} />;
        if (action.type === "START_INTERVIEW") return <StartInterview key={key} action={action} />;
        if (action.type === "REQUEST_COVER_LETTER") return <CoverLetterForm key={key} action={action} />;
        if (action.type === "REVIEW_RESUME")
          return (
            <div key={key}>
              <Button size="M" href={`/resume-review/?documentId=${encodeURIComponent(action.documentId)}`}>
                이력서 내용과 근거 확인하기
              </Button>
            </div>
          );
        if (action.type === "CONDITIONS_SAVED")
          return (
            <p key={key} className="text-small text-grey-800">
              내 프로필에 저장했어요: {action.conditions.join(" · ")}
            </p>
          );
        // 진단 결과 보기(OPEN_DIAGNOSIS)처럼 지금은 쓰지 않는 행동이 지난 대화에 남아 있어도 그리지 않는다
        if (action.type !== "SUGGEST_INTERVIEW") return null;
        return latest ? (
          <div key={key}>
            <Chip onClick={() => onAsk(`${action.job} 직무로 모의면접 체험해 볼래요`)} disabled={busy}>
              ‘{action.job}’ 모의면접 체험해 보기
            </Chip>
          </div>
        ) : null;
      })}
      {latest && (message.followUps ?? []).length > 0 && (
        <div className="flex flex-wrap gap-2">
          {message.followUps?.map((text) => (
            <Chip key={text} onClick={() => onAsk(text)} disabled={busy}>
              {text}
            </Chip>
          ))}
        </div>
      )}
    </div>
  );
}
