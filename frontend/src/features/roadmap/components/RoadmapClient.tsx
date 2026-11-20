"use client";

import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Panel } from "@/components/ui/Panel";
import { TextField } from "@/components/ui/TextField";
import {
  createLearningPath,
  errorMessage,
  getLearningPath,
  poll,
  readFlow,
  safeExternalUrl,
  updateFlow,
} from "@/features/mentoring/api";
import type { LearningPathResponse, MentoringFlow } from "@/features/mentoring/types";

const FORMAT_LABEL: Record<string, string> = { ONLINE: "온라인", OFFLINE: "오프라인", HYBRID: "혼합" };

export function RoadmapClient() {
  const [flow, setFlow] = useState<MentoringFlow | null>(null);
  const [hours, setHours] = useState("8");
  const [format, setFormat] = useState("HYBRID");
  const [targetDate, setTargetDate] = useState("");
  const [result, setResult] = useState<LearningPathResponse | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const restore = useCallback(async () => {
    const current = readFlow();
    setFlow(current);
    if (!current?.learningPathId) {
      setInitializing(false);
      return;
    }
    const learningPathId = current.learningPathId;
    try {
      setResult(await poll(() => getLearningPath(learningPathId)));
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
    const weeklyStudyHours = Number(hours);
    if (!Number.isInteger(weeklyStudyHours) || weeklyStudyHours < 1 || weeklyStudyHours > 40) {
      setError("주당 학습 시간은 1~40시간으로 입력해 주세요.");
      return;
    }
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const created = await createLearningPath({
        analysisId: flow.analysisId,
        weeklyStudyHours,
        preferredFormat: format,
        regionCode: "26",
        targetDate: targetDate || undefined,
        workspaceId: flow.workspaceId,
      });
      if (!created.learningPathId) throw new Error("학습 경로 ID를 받지 못했어요.");
      const nextFlow = updateFlow({ learningPathId: created.learningPathId });
      if (nextFlow) setFlow(nextFlow);
      setResult(await poll(() => getLearningPath(created.learningPathId!)));
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setLoading(false);
    }
  }

  const targetById = useMemo(
    () => new Map((result?.targets ?? []).map((target) => [target.targetId, target.name])),
    [result?.targets],
  );

  if (initializing) return <p role="status" className="text-body text-grey-700">저장된 학습 로드맵을 확인하고 있어요.</p>;
  if (!flow) {
    return (
      <Panel className="flex flex-col items-start gap-3 p-6">
        <p className="text-body text-grey-800">역량 격차를 계산할 직무 진단이 필요해요.</p>
        <Button href="/diagnosis" size="M">이력서·직무 진단하기</Button>
      </Panel>
    );
  }

  return (
    <div className="flex flex-col gap-8">
      <form onSubmit={submit} className="grid gap-5 rounded-card border border-grey-200 p-5 sm:grid-cols-3" noValidate>
        <TextField
          id="weekly-hours"
          label="주당 학습 시간"
          type="number"
          min={1}
          max={40}
          value={hours}
          onChange={(event) => setHours(event.target.value)}
          disabled={loading}
        />
        <label className="flex flex-col gap-2 text-small font-bold text-grey-800">
          선호 방식
          <select
            value={format}
            onChange={(event) => setFormat(event.target.value)}
            disabled={loading}
            className="h-12 rounded-field border border-grey-300 bg-white px-3.75 text-body font-normal text-grey-900 focus:border-blue-500 focus:outline-none"
          >
            <option value="HYBRID">혼합</option>
            <option value="ONLINE">온라인</option>
            <option value="OFFLINE">오프라인</option>
          </select>
        </label>
        <TextField
          id="target-date"
          label="목표일 (선택)"
          type="date"
          value={targetDate}
          onChange={(event) => setTargetDate(event.target.value)}
          disabled={loading}
        />
        <div className="sm:col-span-3">
          <p className="mb-3 text-small text-grey-600">{flow.targetRole} 진단의 확인된 격차와 증빙 보완 항목을 기준으로 만들어요.</p>
          {error && <p role="alert" className="mb-3 rounded-field bg-grey-50 px-4 py-3 text-body text-grey-800">{error}</p>}
          <Button type="submit" disabled={loading}>{loading ? "개인별 로드맵을 만들고 있어요" : "학습 로드맵 생성하기"}</Button>
        </div>
      </form>

      {result && (result.status === "COMPLETED" || result.status === "PARTIAL_SUCCESS") && (
        <section aria-labelledby="roadmap-result-title" className="flex flex-col gap-7">
          <header>
            <h2 id="roadmap-result-title" className="text-h2 font-bold text-grey-900">
              {result.ncsName ?? flow.targetRole} 학습 로드맵
            </h2>
            <p className="mt-1 text-body text-grey-700">
              주 {result.weeklyStudyHours}시간 · {result.totalWeeks}주 · 총 {result.totalHours}시간 · {FORMAT_LABEL[result.preferredFormat ?? ""] ?? result.preferredFormat}
            </p>
            {result.estimated && <p className="mt-1 text-small text-grey-600">기간과 시간은 입력한 주당 학습 시간을 기준으로 한 추정이에요.</p>}
          </header>

          {(result.targets?.length ?? 0) > 0 && (
            <Panel as="section" tone="muted" className="p-5" aria-labelledby="roadmap-order">
              <h3 id="roadmap-order" className="text-small text-grey-600">추천 순서</h3>
              <ol className="mt-2 flex flex-wrap items-center gap-2.5 text-body font-bold text-grey-900">
                {result.targets!.map((target, index) => (
                  <li key={target.targetId} className="flex items-center gap-2.5">
                    <span>{target.name}</span>
                    {index < result.targets!.length - 1 && <ArrowRight aria-hidden className="size-4 text-grey-500" />}
                  </li>
                ))}
              </ol>
            </Panel>
          )}

          {(result.verificationTasks?.length ?? 0) > 0 && (
            <Panel className="p-5">
              <h3 className="text-body font-bold text-grey-900">먼저 사실을 확인할 항목</h3>
              <p className="mt-1 text-small text-grey-600">서류에 없다는 이유만으로 격차로 단정하지 않았어요.</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-grey-700">
                {result.verificationTasks!.map((task) => <li key={task.name}>{task.question ?? task.name}</li>)}
              </ul>
            </Panel>
          )}

          <ol aria-label="주차별 학습 계획" className="flex w-full flex-col border-t border-grey-800">
            {(result.weeks ?? []).map((week) => (
              <li key={week.week} className="flex flex-col gap-2 border-b border-grey-200 py-5.5 sm:flex-row sm:gap-6">
                <p className="w-18 shrink-0 text-body font-bold text-blue-500">{week.week}주차</p>
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <h3 className="text-body font-bold text-grey-900">{week.goals.join(" · ")}</h3>
                  <p className="text-body text-grey-700">{week.activities.join(" · ")}</p>
                  <p className="flex gap-2 text-small"><span className="text-grey-600">산출물</span><span className="font-bold text-grey-800">{week.deliverable}</span></p>
                  {week.officialSources.length > 0 && (
                    <p className="text-small text-grey-600">공식 기준 · {week.officialSources.map((source) => source.name ?? source.unitCode).join(", ")}</p>
                  )}
                </div>
                <div className="shrink-0 text-small text-grey-600 sm:w-42.5 sm:text-right">
                  <p>{week.estimatedHours}시간 · {week.startDate}</p>
                  <p>{week.targetIds.map((id) => targetById.get(id)).filter(Boolean).join(", ")}</p>
                </div>
              </li>
            ))}
          </ol>

          {(result.certificates?.length ?? 0) > 0 && (
            <section aria-labelledby="certificate-title" className="flex flex-col gap-3">
              <h3 id="certificate-title" className="text-h3 font-bold text-grey-900">연계 자격 후보</h3>
              <ul className="grid gap-3 sm:grid-cols-2">
                {result.certificates!.map((certificate) => {
                  const href = safeExternalUrl(certificate.officialUrl);
                  return (
                    <li key={certificate.qualificationCode} className="rounded-card border border-grey-200 p-5">
                      <p className="text-body font-bold text-grey-900">{certificate.name}</p>
                      <p className="mt-1 text-small text-grey-700">{certificate.reason}</p>
                      <p className="mt-2 text-small text-grey-600">{certificate.verificationStatus} · 확인일 {certificate.checkedAt ?? "확인 필요"}</p>
                      {href && <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-block text-small font-medium text-blue-500">공식 정보 보기</a>}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {(result.courses?.length ?? 0) > 0 && (
            <section aria-labelledby="course-title" className="flex flex-col gap-3">
              <h3 id="course-title" className="text-h3 font-bold text-grey-900">현재 확인된 교육과정</h3>
              <ul className="grid gap-3 sm:grid-cols-2">
                {result.courses!.map((course, index) => {
                  const href = safeExternalUrl(course.officialUrl);
                  return (
                    <li key={`${course.title ?? "course"}-${index}`} className="rounded-card border border-grey-200 p-5">
                      <p className="text-body font-bold text-grey-900">{course.title ?? "교육과정"}</p>
                      <p className="mt-1 text-small text-grey-600">확인일 {course.checkedAt ?? "확인 필요"}</p>
                      {href && <a href={href} target="_blank" rel="noreferrer" className="mt-2 inline-block text-small font-medium text-blue-500">공식 모집 정보 보기</a>}
                    </li>
                  );
                })}
              </ul>
            </section>
          )}

          {(result.warnings?.length ?? 0) > 0 && (
            <Panel tone="muted" className="p-5">
              <h3 className="text-body font-bold text-grey-900">출처와 일정 확인 상태</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-small text-grey-700">
                {result.warnings!.map((warning) => <li key={warning.code}>{warning.message}</li>)}
              </ul>
            </Panel>
          )}

          {(result.relatedLinks?.length ?? 0) > 0 && (
            <nav aria-label="관련 공식 안내" className="flex flex-wrap gap-2">
              {result.relatedLinks!.map((link) => {
                const external = safeExternalUrl(link.url);
                const href = external ?? (link.path?.startsWith("/") ? link.path : null);
                return href ? (
                  <a key={`${link.type}-${href}`} href={href} target={external ? "_blank" : undefined} rel={external ? "noreferrer" : undefined} className="rounded-control border border-grey-300 px-3.5 py-2 text-small font-medium text-grey-800">
                    {link.label}
                  </a>
                ) : null;
              })}
            </nav>
          )}

          <div className="flex flex-wrap justify-end gap-2">
            <Button href="/diagnosis/result" variant="secondary">직무 진단 결과</Button>
            <Button href="/jobs">부산 채용 공고 보기</Button>
          </div>
        </section>
      )}
    </div>
  );
}
