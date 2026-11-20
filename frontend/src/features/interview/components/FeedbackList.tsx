import { cn } from "@/lib/cn";
import type { QuestionFeedback } from "../types";

/** 면접 리포트 "질문별 피드백" 목록. 주의할 정면 응시 비율은 red-500으로 보여준다. */
export function FeedbackList({ items }: { items: QuestionFeedback[] }) {
  return (
    <section aria-labelledby="feedback-title" className="flex flex-col gap-2">
      <h2 id="feedback-title" className="text-h2 font-bold text-grey-900">
        질문별 피드백
      </h2>
      <ol className="flex flex-col border-t border-grey-800">
        {items.map((item) => (
          <li key={item.id} className="flex gap-4 border-b border-grey-200 py-4.5 last:border-b-0">
            <span className="w-8 shrink-0 text-body font-bold text-grey-500">{item.label}</span>
            <div className="flex min-w-0 flex-1 flex-col gap-1 sm:flex-row sm:gap-4">
              <div className="flex min-w-0 flex-1 flex-col gap-1">
                <p className="text-body font-bold text-grey-900">{item.topic}</p>
                <p className="text-body text-grey-700">{item.comment}</p>
              </div>
              <dl className="flex shrink-0 gap-3 text-small text-grey-800 sm:w-32.5 sm:flex-col sm:gap-0 sm:text-right">
                <div>
                  <dt className="inline">말하기 </dt>
                  <dd className="inline">{item.speakingSeconds}초</dd>
                </div>
                <div className={cn(item.gazeNeedsAttention && "text-red-500")}>
                  <dt className="inline">정면 응시 </dt>
                  <dd className="inline">
                    {item.frontGazeRate}%{item.gazeNeedsAttention && <span className="sr-only"> (확인 필요)</span>}
                  </dd>
                </div>
              </dl>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
