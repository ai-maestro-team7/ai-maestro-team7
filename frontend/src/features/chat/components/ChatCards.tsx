import { jobDetailHref } from "@/features/jobs/lib";
import { policyDetailHref } from "@/features/policies/lib";
import { Button } from "@/components/ui/Button";
import { asOfLabel, POLICY_STATUS_LABEL } from "../lib";
import type { ChatPolicy, ChatPosting } from "../types";

/** Agent가 찾은 공고 한 장. 숫자 점수 없이 3단계 말로만 보여 준다. */
export function PostingCard({ posting }: { posting: ChatPosting }) {
  const meta = [posting.workRegion, posting.deadline, posting.career].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-col gap-2 rounded-field border border-grey-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <p className="text-small text-grey-600">
            {posting.organization}
            {posting.isSample && " · 팀이 넣어 둔 데이터 (공식 공고 아님)"}
          </p>
          <p className="text-body font-bold text-grey-900">{posting.title}</p>
          <p className="text-small text-grey-600">{meta}</p>
        </div>
        <span className="shrink-0 rounded-control bg-blue-50 px-2 py-1 text-small font-medium text-blue-500">
          {posting.matchLevel}
        </span>
      </div>
      <p className="text-small text-grey-800">급여 {posting.salary}</p>
      {posting.facts.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-small text-grey-600">
          {posting.facts.slice(0, 3).map((fact) => (
            <li key={fact}>· {fact}</li>
          ))}
        </ul>
      )}
      {posting.badges.length > 0 && <p className="text-small text-grey-600">{posting.badges.join(" · ")}</p>}
      <div>
        <Button href={jobDetailHref(posting.jobPostingId)} variant="line" size="M">
          공고 자세히 보기
        </Button>
      </div>
    </li>
  );
}

/** Agent가 찾은 청년정책 한 장. 판정 이유와 출처·기준일을 같이 보여 준다. */
export function PolicyCard({ policy }: { policy: ChatPolicy }) {
  const period = policy.applyStart || policy.applyEnd ? `신청 ${policy.applyStart ?? ""}~${policy.applyEnd ?? ""}` : policy.expected;
  const source = [policy.source, asOfLabel(policy.asOf)].filter(Boolean).join(" · ");
  return (
    <li className="flex flex-col gap-2 rounded-field border border-grey-200 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-body font-bold text-grey-900">{policy.title}</p>
        <span className="shrink-0 rounded-control bg-grey-100 px-2 py-1 text-small font-medium text-grey-800">
          {POLICY_STATUS_LABEL[policy.status] ?? "확인이 필요해요"}
        </span>
      </div>
      {policy.benefit && <p className="text-small text-grey-800">{policy.benefit}</p>}
      {policy.reasons.length > 0 && <p className="text-small text-grey-600">{policy.reasons.slice(0, 2).join(" · ")}</p>}
      {policy.manualChecks.length > 0 && (
        <p className="text-small text-grey-600">직접 확인: {policy.manualChecks.slice(0, 2).join(" · ")}</p>
      )}
      <p className="text-small text-grey-500">{[period, source].filter(Boolean).join(" · ")}</p>
      <div>
        <Button href={policyDetailHref(policy.policyId)} variant="line" size="M">
          정책 자세히 보기
        </Button>
      </div>
    </li>
  );
}
