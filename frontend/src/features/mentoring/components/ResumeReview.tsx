"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { loginHref } from "@/features/auth/lib";
import { useSessionOwner } from "@/features/auth/useSessionOwner";
import { sendChat } from "@/features/chat/api";
import { chatHref } from "@/features/chat/lib";
import { ApiError, confirmProfile, errorMessage, getDocument, getProfile } from "../api";
import type { ProfileResponse, ProfileReviewEntry } from "../types";

type Group = "PROJECT" | "EXPERIENCE" | "CERTIFICATE";
type Decision = "CONFIRM" | "RENAME" | "DELETE" | "NOT_HELD";

function statusLabel(status: string, evidenceLevel: string | undefined, hasEvidence: boolean): string {
  if (evidenceLevel === "USER_CONFIRMED_GAP") return "보유하지 않음을 사용자가 확인함";
  if (status === "VERIFIED") return "사용자가 확인함";
  if (hasEvidence) return "이력서 원문 근거 있음 · 사용자 확인 전";
  if (status === "SUGGESTION") return "AI가 제안한 항목 · 원문 근거 확인 필요";
  return "원문 인용 없음 · 확인 필요";
}

/** 인용문은 이 인증된 화면에서만 A API로 읽는다. 채팅 응답과 모델에는 싣지 않는다. */
export function ResumeReview() {
  const owner = useSessionOwner();
  const documentId = useSearchParams().get("documentId");
  if (!owner) return <Button href={loginHref("/chat/")}>로그인하고 이력서 확인하기</Button>;
  if (!documentId) return <p role="alert">확인할 이력서가 지정되지 않았어요.</p>;
  return <ReviewBody key={`${owner}:${documentId}`} owner={owner} documentId={documentId} />;
}

function ReviewBody({ owner, documentId }: { owner: string; documentId: string }) {
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [state, setState] = useState<"loading" | "processing" | "failed" | "stale" | "ready">("loading");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newSkill, setNewSkill] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const document = await getDocument(documentId);
        if (!active) return;
        if (document.extractionStatus === "FAILED" || document.taskStatus === "FAILED") {
          setState("failed");
          return;
        }
        let latest: ProfileResponse | null = null;
        try {
          latest = await getProfile();
        } catch (failure) {
          if (!(failure instanceof ApiError && failure.status === 404)) throw failure;
        }
        if (!active) return;
        const complete = ["COMPLETED", "REQUIRES_USER_REVIEW"].includes(document.extractionStatus);
        if (latest?.sourceDocumentIds?.includes(documentId) && complete) {
          setProfile(latest);
          setState("ready");
          return;
        }
        if (complete && latest && !latest.sourceDocumentIds?.includes(documentId)) {
          setState("stale");
          return;
        }
        setState("processing");
        timer = setTimeout(load, 2000);
      } catch (failure) {
        if (!active) return;
        setError(errorMessage(failure));
        setState("failed");
      }
    }
    void load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [owner, documentId, revision]);

  async function decide(group: Group | "SKILL", itemId: string, action: Decision, name?: string) {
    if (!profile || busy) return;
    setBusy(true);
    setError(null);
    try {
      const change = group === "SKILL"
        ? { decisions: [{ skillId: itemId, action, ...(name ? { name } : {}) }] }
        : { entryDecisions: [{ group, itemId, action: action as "CONFIRM" | "RENAME" | "DELETE",
                             ...(name ? { name } : {}) }] };
      const updated = await confirmProfile(profile, change);
      setProfile(updated);
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 409
        ? "다른 곳에서 프로필이 바뀌었어요. 최신 내용을 다시 불러왔습니다. 확인 후 다시 저장해 주세요."
        : errorMessage(failure));
      if (failure instanceof ApiError && failure.status === 409) setRevision((value) => value + 1);
    } finally {
      setBusy(false);
    }
  }

  async function addSkill() {
    if (!profile || !newSkill.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      setProfile(await confirmProfile(profile, { additions: [{ name: newSkill.trim() }] }));
      setNewSkill("");
    } catch (failure) {
      setError(failure instanceof ApiError && failure.status === 409
        ? "프로필이 바뀌었어요. 최신 내용을 다시 불러왔습니다." : errorMessage(failure));
      if (failure instanceof ApiError && failure.status === 409) setRevision((value) => value + 1);
    } finally {
      setBusy(false);
    }
  }

  async function findJobs() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const started = await sendChat({ message: "내가 확인한 이력서 역량을 바탕으로 맞는 공고와 청년정책 찾아줘" });
      router.push(chatHref(started.sessionId));
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  const quotes = (ids: string[]) => (profile?.evidence ?? []).filter((e) => ids.includes(e.evidenceId) && e.sourceDocumentId === documentId);

  return (
    <main className="flex w-full max-w-180 flex-col gap-5">
      <h1 className="text-h2 font-bold text-grey-900">이력서 내용과 원문 근거 확인</h1>
      <p className="text-body text-grey-700">AI가 찾은 항목은 확인 전 상태예요. 원문을 보고 맞는 항목만 확인해 주세요.</p>
      {state === "loading" || state === "processing" ? (
        <p role="status">{state === "loading" ? "내용을 불러오고 있어요." : "이력서를 분석 중이에요. 완료되면 여기서 확인할 수 있어요."}</p>
      ) : null}
      {state === "stale" && <p role="alert">이후에 다른 이력서를 올려 최신 프로필이 바뀌었어요. 이 문서의 결과로 표시하지 않습니다.</p>}
      {state === "failed" && <p role="alert">이력서 처리를 완료하지 못했어요. {error ?? "다시 올려 주세요."}</p>}
      {error && state === "ready" && <p role="alert" className="text-red-500">{error}</p>}
      {state === "ready" && profile && (
        <>
          <p className="text-small text-grey-600">프로필 버전 {profile.profileVersion} · 인용문은 이 화면에서만 보여드려요.</p>
          <section className="flex flex-col gap-3" aria-label="역량">
            <h2 className="text-h3 font-bold">역량</h2>
            {profile.skills.map((item) => (
              <ReviewItem key={item.skillId} name={item.name} status={item.factStatus} evidenceLevel={item.evidenceLevel}
                evidence={quotes(item.evidenceIds)} busy={busy}
                onDecide={(action, name) => void decide("SKILL", item.skillId, action, name)} skill />
            ))}
            <div className="flex gap-2">
              <input value={newSkill} onChange={(event) => setNewSkill(event.target.value)} maxLength={50}
                aria-label="추가할 역량" placeholder="빠진 역량 직접 추가" className="min-w-0 flex-1 rounded-control border border-grey-300 px-3" />
              <Button size="M" onClick={() => void addSkill()} disabled={busy || !newSkill.trim()}>추가</Button>
            </div>
            <p className="text-small text-grey-600">직접 추가한 역량은 이력서 인용 근거가 없는 본인 입력으로 표시돼요.</p>
          </section>
          {([ ["PROJECT", "프로젝트", profile.projects], ["EXPERIENCE", "경험", profile.experiences],
              ["CERTIFICATE", "자격", profile.certificates] ] as [Group, string, ProfileReviewEntry[]][]).map(([group, label, items]) => (
            <section key={group} className="flex flex-col gap-3" aria-label={label}>
              <h2 className="text-h3 font-bold">{label}</h2>
              {items.length ? items.map((item) => (
                <ReviewItem key={item.itemId} name={item.name} detail={[item.summary, item.period].filter(Boolean).join(" · ")}
                  status={item.factStatus} evidence={quotes(item.evidenceIds)} busy={busy}
                  onDecide={(action, name) => void decide(group, item.itemId, action, name)} />
              )) : <p className="text-small text-grey-600">찾은 항목이 없어요.</p>}
            </section>
          ))}
          {profile.needsConfirmation?.length > 0 && (
            <section><h2 className="text-h3 font-bold">추가 확인이 필요한 내용</h2>
              <ul className="list-disc pl-6">{profile.needsConfirmation.map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          )}
          <Button onClick={() => void findJobs()} disabled={busy}>확인한 내용으로 공고 찾기</Button>
        </>
      )}
      <Button href="/chat/" variant="line">채팅으로 돌아가기</Button>
    </main>
  );
}

function ReviewItem({ name, detail, status, evidenceLevel, evidence, busy, onDecide, skill = false }: {
  name: string; detail?: string; status: string; evidenceLevel?: string;
  evidence: Array<{ evidenceId: string; page: number; quotedText: string }>;
  busy: boolean; skill?: boolean;
  onDecide: (action: Decision, name?: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [renamed, setRenamed] = useState(name);
  const label = statusLabel(status, evidenceLevel, evidence.length > 0);
  return (
    <article className="rounded-card border border-grey-200 p-4">
      <h3 className="text-body font-bold text-grey-900">{name}</h3>
      {detail && <p className="text-small text-grey-700">{detail}</p>}
      <p className="text-small text-grey-600">{label}{evidenceLevel === "PARTIAL" ? " · 부분 근거" : ""}</p>
      {evidence.map((quote) => <blockquote key={quote.evidenceId} className="mt-2 border-l-2 border-grey-300 pl-3 text-small text-grey-700">
        {quote.quotedText} <span className="text-grey-500">(원문 {quote.page}쪽)</span>
      </blockquote>)}
      {editing && <div className="mt-3 flex gap-2">
        <input value={renamed} onChange={(event) => setRenamed(event.target.value)} maxLength={50}
          aria-label={`${name} 이름 수정`} className="min-w-0 flex-1 rounded-control border border-grey-300 px-3" />
        <Button size="M" onClick={() => { onDecide("RENAME", renamed.trim()); setEditing(false); }} disabled={busy || !renamed.trim()}>수정 저장</Button>
      </div>}
      <div className="mt-3 flex flex-wrap gap-2">
        {status !== "VERIFIED" && <Button size="M" onClick={() => onDecide("CONFIRM")} disabled={busy}>맞아요</Button>}
        <Button size="M" variant="line" onClick={() => { setRenamed(name); setEditing((value) => !value); }} disabled={busy}>이름 수정</Button>
        {skill && <Button size="M" variant="line" onClick={() => onDecide("NOT_HELD")} disabled={busy}>보유하지 않아요</Button>}
        <Button size="M" variant="line" onClick={() => onDecide("DELETE")} disabled={busy}>잘못 추출됨</Button>
      </div>
    </article>
  );
}
