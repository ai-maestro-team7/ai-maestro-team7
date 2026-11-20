"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { SubTabs } from "@/components/ui/SubTabs";
import { TextArea } from "@/components/ui/TextArea";
import { TextField } from "@/components/ui/TextField";
import {
  createReview,
  errorMessage,
  getReview,
  poll,
  readFlow,
  updateFlow,
} from "@/features/mentoring/api";
import type { MentoringFlow, ReviewResponse } from "@/features/mentoring/types";
import type { ReviewDocumentKind } from "../types";

const DOCUMENT_TABS = [
  { key: "COVER_LETTER" as const, label: "자기소개서" },
  { key: "RESUME" as const, label: "이력서 문장" },
];

function factCheckLabel(value: string): string {
  if (value === "REJECTED") return "원문에서 확인되지 않아 예시를 만들지 않았어요";
  if (value === "VERIFIED") return "원문·확인된 경험과 일치해요";
  return "사실 확인이 필요해요";
}

export function ReviewClient() {
  const [flow, setFlow] = useState<MentoringFlow | null>(null);
  const [kind, setKind] = useState<ReviewDocumentKind>("COVER_LETTER");
  const [text, setText] = useState("");
  const [question, setQuestion] = useState("직무 관련 경험을 설명해 주세요");
  const [maxCharacters, setMaxCharacters] = useState("1000");
  const [result, setResult] = useState<ReviewResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState("");
  const [textError, setTextError] = useState("");

  const restore = useCallback(async () => {
    const current = readFlow();
    setFlow(current);
    if (!current?.reviewId) {
      setInitializing(false);
      return;
    }
    const reviewId = current.reviewId;
    try {
      setResult(await poll(() => getReview(reviewId)));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setInitializing(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void restore(), 0);
    return () => window.clearTimeout(timer);
  }, [restore]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!flow) return;
    if (text.trim().length < 50) {
      setTextError("첨삭할 문장을 50자 이상 입력해 주세요.");
      return;
    }
    const limit = Number(maxCharacters);
    if (!Number.isInteger(limit) || limit < 1 || limit > 5000) {
      setError("글자 수 제한은 1~5,000 사이로 입력해 주세요.");
      return;
    }
    setTextError("");
    setError("");
    setLoading(true);
    setResult(null);
    try {
      const created = await createReview({
        inputText: text.trim(),
        documentType: kind,
        analysisId: flow.analysisId,
        workspaceId: flow.workspaceId,
        questionText: question.trim() || undefined,
        maxCharacters: limit,
      });
      if (!created.reviewId) throw new Error("첨삭 ID를 받지 못했어요.");
      const nextFlow = updateFlow({ reviewId: created.reviewId });
      if (nextFlow) setFlow(nextFlow);
      setResult(await poll(() => getReview(created.reviewId!)));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  if (initializing) return <p role="status" className="text-body text-grey-700">이전 첨삭 결과를 확인하고 있어요.</p>;
  if (!flow) {
    return (
      <Panel className="flex flex-col items-start gap-3 p-6">
        <p className="text-body text-grey-800">첨삭 기준이 될 직무 진단이 필요해요.</p>
        <Button href="/diagnosis" size="M">이력서·직무 진단하기</Button>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
        <div className="flex flex-col gap-3">
          <SubTabs
            label="첨삭할 문서"
            items={DOCUMENT_TABS}
            activeKey={kind}
            onChange={setKind}
            panelId="review-input"
          />
          <p className="text-small text-grey-600">진단 기준 · {flow.targetRole} · NCS {flow.targetNcsCode}</p>
        </div>
        <div id="review-input" role="tabpanel" className="flex flex-col gap-5">
          <TextArea
            id="review-text"
            label="첨삭할 원문"
            value={text}
            onChange={(event) => setText(event.target.value)}
            rows={8}
            maxLength={10000}
            placeholder="실제 경험과 본인이 한 일을 사실대로 적어 주세요. 없는 수치나 성과는 만들지 않아요."
            error={textError}
            disabled={loading}
          />
          <TextField
            id="review-question"
            label="자기소개서 문항"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={300}
            disabled={loading}
          />
          <TextField
            id="review-limit"
            label="글자 수 제한"
            type="number"
            min={1}
            max={5000}
            value={maxCharacters}
            onChange={(event) => setMaxCharacters(event.target.value)}
            disabled={loading}
          />
        </div>
        {error && <p role="alert" className="rounded-field bg-grey-50 px-4 py-3 text-body text-grey-800">{error}</p>}
        <div><Button type="submit" disabled={loading}>{loading ? "AI가 근거를 확인하고 있어요" : "실제 문장 첨삭하기"}</Button></div>
      </form>

      {result && (result.status === "COMPLETED" || result.status === "PARTIAL_SUCCESS") && (
        <section aria-labelledby="review-result-title" className="flex flex-col gap-5 border-t border-grey-200 pt-7">
          <div>
            <h2 id="review-result-title" className="text-h2 font-bold text-grey-900">첨삭 결과</h2>
            <p className="mt-1 text-body text-grey-700">{result.overallFeedback}</p>
            {result.charCount && (
              <p className="mt-1 text-small text-grey-600">
                공백 포함 {result.charCount.withSpaces}자 · UTF-8 {result.charCount.utf8Bytes}바이트
                {result.charCount.overLimit ? " · 입력한 글자 수 제한을 넘었어요" : ""}
              </p>
            )}
          </div>

          {(result.strengths?.length ?? 0) > 0 && (
            <Panel tone="muted" className="p-5">
              <h3 className="text-body font-bold text-grey-900">잘 드러난 점</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-grey-700">
                {result.strengths!.map((strength) => <li key={strength}>{strength}</li>)}
              </ul>
            </Panel>
          )}

          <ol className="flex flex-col gap-3">
            {(result.issues ?? []).map((issue, index) => (
              <li key={issue.issueId} className="rounded-card border border-grey-200 p-5">
                <p className="text-small font-bold text-blue-500">{index + 1}. {issue.issueType}</p>
                {issue.originalText && <p className="mt-2 border-l-2 border-grey-300 pl-3 text-body text-grey-800">{issue.originalText}</p>}
                <p className="mt-3 text-body text-grey-700">{issue.reason}</p>
                <p className="mt-2 text-body font-bold text-grey-900">개선 방향 · {issue.improvementAction}</p>
                {issue.revisedExample && issue.factCheck !== "REJECTED" && (
                  <p className="mt-2 rounded-field bg-blue-50 p-3 text-body text-grey-900">{issue.revisedExample}</p>
                )}
                <p className="mt-2 text-small text-grey-600">{factCheckLabel(issue.factCheck)}</p>
                {issue.questions.length > 0 && (
                  <ul className="mt-2 space-y-1 text-small text-grey-800">
                    {issue.questions.map((item) => <li key={item}>확인 질문 · {item}</li>)}
                  </ul>
                )}
              </li>
            ))}
          </ol>

          {((result.missingQuestions?.length ?? 0) > 0 || (result.warnings?.length ?? 0) > 0) && (
            <Panel tone="muted" className="p-5">
              <h3 className="text-body font-bold text-grey-900">제출 전에 확인해 주세요</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-grey-700">
                {result.missingQuestions?.map((item) => <li key={item}>{item}</li>)}
                {result.warnings?.map((item) => <li key={item.code}>{item.message}</li>)}
              </ul>
            </Panel>
          )}

          <div className="flex justify-end gap-2">
            <Button href="/diagnosis/result" variant="secondary" size="M">직무 진단 결과</Button>
            <Button href="/roadmap" size="M">학습 로드맵 만들기</Button>
          </div>
        </section>
      )}
    </div>
  );
}
