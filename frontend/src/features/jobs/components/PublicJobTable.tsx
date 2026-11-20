import Link from "next/link";
import { type Column, DataTable, DataTableSkeleton, TableCell, TableRow } from "@/components/ui/DataTable";
import { cn } from "@/lib/cn";
import {
  CAREER_LABELS,
  deadlineLines,
  displayTitle,
  EMPLOYMENT_LABELS,
  jobDetailHref,
  ORG_TYPE_LABELS,
  orgPayText,
} from "../lib";
import type { PublicPostingCard } from "../types";

/** 로그인 없이 보는 공고 표. 맞춤 표(JobTable)의 적합도·저장 열 대신 경력·고용 형태 열이 있다. */
const COLUMNS = {
  company: "w-45 shrink-0",
  posting: "min-w-0 flex-1",
  place: "w-40 shrink-0",
  terms: "w-28 shrink-0",
  deadline: "w-25 shrink-0",
} as const;

const PUBLIC_COLUMNS: Column[] = [
  { key: "company", label: "기업·기관", className: COLUMNS.company },
  { key: "posting", label: "공고", className: COLUMNS.posting },
  { key: "place", label: "근무지 · 구분", className: COLUMNS.place },
  { key: "terms", label: "경력 · 고용", className: COLUMNS.terms },
  { key: "deadline", label: "마감", className: COLUMNS.deadline },
];

const ROW_INSET = "px-4";

/** 공고 아래 작은 줄: 직무, 배지(출처가 있는 것만 서버가 보낸다) */
function subline(job: PublicPostingCard): string {
  const parts = [job.job.name, ...job.badges.map((badge) => badge.label)];
  if (job.isSample) parts.push("예시 데이터");
  return parts.filter(Boolean).join(" · ");
}

function careerText(job: PublicPostingCard): string {
  return job.careerType === "UNKNOWN" ? "공고 확인" : CAREER_LABELS[job.careerType];
}

function employmentText(job: PublicPostingCard): string {
  return job.employmentType === "UNKNOWN" ? "고용 형태 공고 확인" : EMPLOYMENT_LABELS[job.employmentType];
}

/** 행 전체가 공고 상세 링크다. 상세는 로그인해야 보이고, 로그인 전이면 상세 화면이 로그인 안내를 보여 준다. */
function PublicJobRow({ job, asOf }: { job: PublicPostingCard; asOf: string }) {
  const deadline = deadlineLines(job.closesAt, job.rolling, asOf);
  return (
    <TableRow className={cn("relative py-4 hover:bg-grey-50", ROW_INSET)}>
      <TableCell className={cn(COLUMNS.company, "flex flex-col justify-center gap-0.5")}>
        <span className="truncate text-body font-medium text-grey-900" title={job.organization}>
          {job.organization}
        </span>
        {job.orgPay && (
          <span className="truncate text-small text-grey-600" title={`${job.orgPay.year}년 결산 · ${job.orgPay.source}`}>
            {orgPayText(job.orgPay.average)}
          </span>
        )}
      </TableCell>
      <TableCell className={cn(COLUMNS.posting, "flex flex-col gap-0.5")}>
        <Link
          href={jobDetailHref(job.jobPostingId)}
          className="truncate text-body font-bold text-grey-900 after:absolute after:inset-0 after:content-['']"
          title={job.title}
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
      <TableCell className={cn(COLUMNS.terms, "flex flex-col")}>
        <span className="truncate text-body text-grey-800">{careerText(job)}</span>
        <span className="truncate text-small text-grey-600">{employmentText(job)}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.deadline, "flex flex-col")}>
        <span className="text-body text-grey-800">{deadline.main}</span>
        <span className="text-small text-grey-600">{deadline.sub}</span>
      </TableCell>
    </TableRow>
  );
}

export function PublicJobTable({ jobs, asOf }: { jobs: PublicPostingCard[]; asOf: string }) {
  return (
    <DataTable columns={PUBLIC_COLUMNS} label="채용 공고 목록" headerClassName={ROW_INSET}>
      {jobs.map((job) => (
        <PublicJobRow key={job.jobPostingId} job={job} asOf={asOf} />
      ))}
    </DataTable>
  );
}

export function PublicJobTableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <DataTableSkeleton
      columns={PUBLIC_COLUMNS}
      label="공고를 불러오는 중"
      rows={rows}
      headerClassName={ROW_INSET}
      rowClassName={cn("py-4", ROW_INSET)}
    />
  );
}
