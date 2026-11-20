import { type Column, DataTable, TableCell, TableRow } from "@/components/ui/DataTable";
import { StatusDot, type StatusTone } from "@/components/ui/StatusDot";
import { cn } from "@/lib/cn";
import type { RequirementCheck, RequirementStatus } from "../types";

const STATUS: Record<RequirementStatus, { label: string; tone: StatusTone }> = {
  MET: { label: "충족", tone: "green" },
  GAP: { label: "보완 필요", tone: "red" },
  EVIDENCE: { label: "증빙 보완", tone: "orange" },
};

/** 열 폭 (Figma: 요구 역량 268, 상태 140, 근거 260) */
const COLUMNS = {
  name: "w-67 shrink-0",
  status: "w-35 shrink-0",
  evidence: "min-w-0 flex-1",
} as const;

const REQUIREMENT_COLUMNS: Column[] = [
  { key: "name", label: "요구 역량", className: COLUMNS.name },
  { key: "status", label: "상태", className: COLUMNS.status },
  { key: "evidence", label: "근거", className: COLUMNS.evidence },
];

/** 직무 요구 역량 비교 표 */
export function RequirementTable({ items }: { items: RequirementCheck[] }) {
  return (
    <DataTable columns={REQUIREMENT_COLUMNS} label="직무 요구 역량 비교" minWidthClassName="min-w-150">
      {items.map((item) => {
        const status = STATUS[item.status];
        return (
          <TableRow key={item.name} className="py-4">
            <TableCell className={cn(COLUMNS.name, "text-body font-medium text-grey-900")}>{item.name}</TableCell>
            <TableCell className={COLUMNS.status}>
              <StatusDot tone={status.tone} label={status.label} />
            </TableCell>
            <TableCell className={cn(COLUMNS.evidence, "text-small text-grey-600")}>{item.evidence}</TableCell>
          </TableRow>
        );
      })}
    </DataTable>
  );
}
