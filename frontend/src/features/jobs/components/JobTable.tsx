import Link from "next/link";
import { type Column, DataTable, DataTableSkeleton, TableCell, TableRow } from "@/components/ui/DataTable";
import { cn } from "@/lib/cn";
import { deadlineLines, displayTitle, jobDetailHref, MATCH_LABELS, matchReason, ORG_TYPE_LABELS, orgPayText, orgPayYear } from "../lib";
import type { PostingCard } from "../types";
import { SaveToggle } from "./SaveToggle";

/** 공고 표 열 (Figma JobRow 27:1640 폭: 기업 180, 근무지 140, 마감 100, 적합도 170, 저장 20) */
const COLUMNS = {
  company: "w-45 shrink-0",
  posting: "min-w-0 flex-1",
  place: "w-35 shrink-0",
  deadline: "w-25 shrink-0",
  match: "w-42.5 shrink-0",
  save: "w-5 shrink-0",
} as const;

const JOB_COLUMNS: Column[] = [
  { key: "company", label: "기업·기관", className: COLUMNS.company },
  { key: "posting", label: "공고", className: COLUMNS.posting },
  { key: "place", label: "근무지 · 기관 유형", className: COLUMNS.place },
  { key: "deadline", label: "마감", className: COLUMNS.deadline },
  { key: "match", label: "나와의 적합도", className: COLUMNS.match },
  { key: "save", label: "저장", className: COLUMNS.save, srOnly: true },
];

/** 머리줄과 행에 같이 주는 좌우 여백 */
const ROW_INSET = "px-4";

/** 공고 아래 작은 줄: 직종, 배지(출처가 있는 것만 서버가 보낸다), 부산 대안 수 */
function subline(job: PostingCard): string {
  const parts = [job.job.name, ...job.badges.map((badge) => badge.label)];
  if (job.busanAlternativesCount) parts.push(`부산에서 비슷한 공고 ${job.busanAlternativesCount}개`);
  if (job.isSample) parts.push("예시 데이터");
  return parts.filter(Boolean).join(" · ");
}

/** Figma JobRow. 행 전체가 공고 상세 링크이고, 저장 버튼만 따로 누를 수 있다. */
export function JobRow({ job, asOf }: { job: PostingCard; asOf: string }) {
  const deadline = deadlineLines(job.closesAt, job.rolling, asOf);
  return (
    <TableRow className={cn("group relative py-4 transition-colors hover:bg-grey-50", ROW_INSET)}>
      <TableCell className={cn(COLUMNS.company, "flex flex-col justify-center gap-0.5")}>
        <span className="truncate text-body font-medium text-grey-900">{job.organization}</span>
        {job.orgPay && (
          <span className="truncate text-small text-grey-600" title={`${orgPayYear(job.orgPay.year, job.orgPay.yearNote)} · ${job.orgPay.source}`}>
            {orgPayText(job.orgPay.average)}
          </span>
        )}
      </TableCell>
      <TableCell className={cn(COLUMNS.posting, "flex flex-col gap-0.5")}>
        {/* after:inset-0 으로 행 전체를 링크 영역으로 넓힌다 */}
        <Link
          href={jobDetailHref(job.jobPostingId)}
          title={job.title}
          className="truncate text-body font-bold text-grey-900 transition-colors group-hover:text-blue-500 after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-blue-500"
        >
          {displayTitle(job.title)}
        </Link>
        <span className="truncate text-small text-grey-600" title={subline(job)}>
          {subline(job)}
        </span>
      </TableCell>
      <TableCell className={cn(COLUMNS.place, "flex flex-col")}>
        <span className="text-body break-keep text-grey-800">{job.workRegion.label}</span>
        <span className="text-small text-grey-600">{ORG_TYPE_LABELS[job.orgType]}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.deadline, "flex flex-col")}>
        <span className="text-body text-grey-800">{deadline.main}</span>
        <span className="text-small text-grey-600">{deadline.sub}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.match, "flex flex-col gap-0.5")}>
        <span className={cn("text-body font-bold", job.matchLevel === "GOOD" ? "text-blue-500" : "text-grey-900")}>
          {MATCH_LABELS[job.matchLevel]}
        </span>
        {job.regionalTalent === "LIKELY" ? (
          <span className="truncate text-small font-medium text-blue-500">지역 혜택 대상일 수 있음</span>
        ) : (
          <span className="truncate text-small text-grey-600" title={matchReason(job.facts)}>
            {matchReason(job.facts)}
          </span>
        )}
      </TableCell>
      <TableCell className={COLUMNS.save}>
        <SaveToggle jobPostingId={job.jobPostingId} jobTitle={`${job.organization} ${job.title}`} />
      </TableCell>
    </TableRow>
  );
}

export function JobTable({ jobs, asOf }: { jobs: PostingCard[]; asOf: string }) {
  return (
    <DataTable columns={JOB_COLUMNS} label="채용 공고 목록" headerClassName={ROW_INSET}>
      {jobs.map((job) => (
        <JobRow key={job.jobPostingId} job={job} asOf={asOf} />
      ))}
    </DataTable>
  );
}

/** 공고를 불러오는 동안 보여주는 표 자리 */
export function JobTableSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <DataTableSkeleton
      columns={JOB_COLUMNS}
      label="공고를 불러오는 중"
      rows={rows}
      headerClassName={ROW_INSET}
      rowClassName={cn("py-4", ROW_INSET)}
    />
  );
}
