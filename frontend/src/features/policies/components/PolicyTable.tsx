import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { type Column, DataTable, DataTableSkeleton, TableCell, TableRow } from "@/components/ui/DataTable";
import { StatusDot } from "@/components/ui/StatusDot";
import { cn } from "@/lib/cn";
import { applyPeriod, firstLine, POLICY_STATUS, policyDetailHref } from "../lib";
import type { PolicyCard } from "../types";

/** 정책 표 열 (Figma PolicyRow 27:1655 폭: 지원 내용 170, 추천 대상 190, 확인할 조건 200, 상태 140, 화살표 18) */
const COLUMNS = {
  policy: "min-w-0 flex-1",
  benefit: "w-42.5 shrink-0",
  target: "w-47.5 shrink-0",
  conditions: "w-50 shrink-0",
  status: "w-35 shrink-0",
  arrow: "w-4.5 shrink-0",
} as const;

const POLICY_COLUMNS: Column[] = [
  { key: "policy", label: "정책", className: COLUMNS.policy },
  { key: "benefit", label: "지원 내용", className: COLUMNS.benefit },
  { key: "target", label: "판정 근거", className: COLUMNS.target },
  { key: "conditions", label: "신청 기간", className: COLUMNS.conditions },
  { key: "status", label: "상태", className: COLUMNS.status },
  { key: "arrow", label: "상세", className: COLUMNS.arrow, srOnly: true },
];

/** Figma PolicyRow. 행 전체가 정책 상세 링크다. */
export function PolicyRow({ policy }: { policy: PolicyCard }) {
  const status = POLICY_STATUS[policy.eligibility.status];
  const reasons = [...policy.eligibility.reasons, ...policy.eligibility.manualChecks];
  return (
    <TableRow className="relative py-4.5 hover:bg-grey-50">
      <TableCell className={COLUMNS.policy}>
        <Link
          href={policyDetailHref(policy.policyId)}
          className="line-clamp-2 text-body font-bold text-grey-900 after:absolute after:inset-0 after:content-['']"
        >
          {policy.title}
        </Link>
      </TableCell>
      <TableCell className={cn(COLUMNS.benefit, "line-clamp-2 text-body text-grey-800")}>
        {firstLine(policy.benefit?.text ?? policy.summary) || "상세에서 확인"}
      </TableCell>
      <TableCell className={cn(COLUMNS.target, "line-clamp-2 text-body text-grey-800")}>
        {reasons.length > 0 ? reasons.join(" · ") : "확인 필요"}
      </TableCell>
      <TableCell className={cn(COLUMNS.conditions, "text-body text-grey-800")}>
        {applyPeriod(policy.application)}
      </TableCell>
      <TableCell className={COLUMNS.status}>
        <StatusDot tone={status.tone} label={status.label} />
      </TableCell>
      <TableCell className={cn(COLUMNS.arrow, "text-grey-400")}>
        <ChevronRight aria-hidden className="size-4.5" strokeWidth={2} />
      </TableCell>
    </TableRow>
  );
}

export function PolicyTable({ policies }: { policies: PolicyCard[] }) {
  return (
    <DataTable columns={POLICY_COLUMNS} label="청년 지원 정책 목록">
      {policies.map((policy) => (
        <PolicyRow key={policy.policyId} policy={policy} />
      ))}
    </DataTable>
  );
}

/** 정책을 불러오는 동안 보여주는 표 자리 */
export function PolicyTableSkeleton({ rows = 3 }: { rows?: number }) {
  return <DataTableSkeleton columns={POLICY_COLUMNS} label="정책을 불러오는 중" rows={rows} rowClassName="py-4.5" />;
}
