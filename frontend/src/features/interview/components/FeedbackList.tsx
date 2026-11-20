import type { ReportQuestion } from "../types";

const REASON_TEXT: Record<string, string> = {
  NO_ANSWER: "말을 인식하지 못해 평가하지 않았어요.",
  TRANSCRIBE_FAILED: "음성을 글로 바꾸지 못해 평가하지 않았어요.",
};

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="inline">{label} </dt>
      <dd className="inline font-medium text-grey-900">{value}</dd>
    </div>
  );
}

function Points({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="flex flex-col gap-1">
      <p className="text-small font-bold text-grey-700">{title}</p>
      <ul className="flex flex-col gap-0.5">
        {items.map((item) => (
          <li key={item} className="flex gap-2 text-body text-grey-800">
            <span aria-hidden className="text-grey-400">
              ·
            </span>
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 면접 리포트 "질문별 피드백". 점수와 측정값은 서버가 계산한 값을 그대로 보여준다. */
export function FeedbackList({ items }: { items: ReportQuestion[] }) {
  return (
    <section aria-labelledby="feedback-title" className="flex flex-col gap-2">
      <h2 id="feedback-title" className="text-h2 font-bold text-grey-900">
        질문별 피드백
      </h2>
      <ol className="flex flex-col border-t border-grey-800">
        {items.map((item, index) => {
          const { metrics } = item;
          return (
            <li key={item.questionId} className="flex gap-4 border-b border-grey-200 py-5 last:border-b-0">
              <span className="w-8 shrink-0 text-body font-bold text-grey-500">Q{index + 1}</span>
              <div className="flex min-w-0 flex-1 flex-col gap-3.5">
                <div className="flex flex-col gap-1">
                  <p className="text-body font-bold text-grey-900">{item.question}</p>
                  {item.followUp && <p className="text-small text-grey-600">추가 질문 · {item.followUp.question}</p>}
                </div>

                {item.evaluable ? (
                  <>
                    {item.comment && <p className="text-body text-grey-800">{item.comment}</p>}
                    <Points title="잘한 점" items={item.strengths} />
                    <Points title="보완할 점" items={item.improvements} />
                    {item.direction && (
                      <div className="flex flex-col gap-1">
                        <p className="text-small font-bold text-grey-700">다음에는</p>
                        <p className="text-body text-grey-800">{item.direction}</p>
                      </div>
                    )}
                  </>
                ) : (
                  <p className="text-body text-grey-700">{item.comment ?? REASON_TEXT[item.reason ?? ""] ?? "평가하지 않은 질문이에요."}</p>
                )}

                <dl className="flex flex-wrap gap-x-5 gap-y-1 text-small text-grey-600">
                  {item.contentScore !== null && <Metric label="내용" value={`${item.contentScore}점`} />}
                  {metrics.speechRate !== null && <Metric label="말 속도" value={`분당 ${Math.round(metrics.speechRate)}음절`} />}
                  {metrics.longPausePerMin !== null && <Metric label="긴 침묵" value={`분당 ${metrics.longPausePerMin}회`} />}
                  {metrics.frontalRatio !== null && <Metric label="정면 응시" value={`${metrics.frontalRatio}%`} />}
                  {metrics.timeLimitReached && <Metric label="시간" value="2분을 넘겨 자동 제출" />}
                </dl>

                {(item.answerText || item.followUp?.answerText) && (
                  <details className="text-small text-grey-700">
                    <summary className="cursor-pointer font-medium text-grey-700">내 답변 보기</summary>
                    <div className="mt-2 flex flex-col gap-2 rounded-field bg-grey-50 px-4 py-3">
                      {item.answerText && <p className="whitespace-pre-wrap">{item.answerText}</p>}
                      {item.followUp?.answerText && (
                        <p className="whitespace-pre-wrap">
                          <span className="font-medium text-grey-600">추가 질문 답변 · </span>
                          {item.followUp.answerText}
                        </p>
                      )}
                    </div>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
