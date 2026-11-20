import Link from "next/link";
import { type Column, DataTable, TableCell, TableRow } from "@/components/ui/DataTable";
import { cn } from "@/lib/cn";
import { deadlineLines, MATCH_LABELS } from "../lib";
import type { JobPosting } from "../types";
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
  { key: "company", label: "기업", className: COLUMNS.company },
  { key: "posting", label: "공고", className: COLUMNS.posting },
  { key: "place", label: "근무지 · 고용 형태", className: COLUMNS.place },
  { key: "deadline", label: "마감", className: COLUMNS.deadline },
  { key: "match", label: "나와의 적합도", className: COLUMNS.match },
  { key: "save", label: "저장", className: COLUMNS.save, srOnly: true },
];

/** Figma JobRow. 행 전체가 공고 상세 링크이고, 저장 버튼만 따로 누를 수 있다. */
export function JobRow({ job, asOf }: { job: JobPosting; asOf: string }) {
  const deadline = deadlineLines(job, asOf);
  return (
    <TableRow className="relative py-4 hover:bg-grey-50">
      <TableCell className={cn(COLUMNS.company, "flex items-center gap-3")}>
        <span
          aria-hidden
          className="flex size-10 shrink-0 items-center justify-center rounded-control bg-grey-100 text-small font-bold text-grey-600"
        >
          {job.companyInitial}
        </span>
        <span className="truncate text-body font-medium text-grey-900">{job.company}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.posting, "flex flex-col gap-0.5")}>
        {/* after:inset-0 으로 행 전체를 링크 영역으로 넓힌다 */}
        <Link
          href={`/jobs/${job.id}`}
          className="truncate text-body font-bold text-grey-900 after:absolute after:inset-0 after:content-['']"
        >
          {job.title}
        </Link>
        <span className="truncate text-small text-grey-600">{job.skills.join(" · ")}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.place, "text-body text-grey-800")}>
        {job.district} · {job.employmentType}
      </TableCell>
      <TableCell className={cn(COLUMNS.deadline, "flex flex-col")}>
        <span className="text-body text-grey-800">{deadline.main}</span>
        <span className="text-small text-grey-600">{deadline.sub}</span>
      </TableCell>
      <TableCell className={cn(COLUMNS.match, "flex flex-col gap-0.5")}>
        <span className={cn("text-body font-bold", job.match.level === "GOOD" ? "text-blue-500" : "text-grey-900")}>
          {MATCH_LABELS[job.match.level]}
        </span>
        <span className="truncate text-small text-grey-600">{job.match.reason}</span>
      </TableCell>
      <TableCell className={COLUMNS.save}>
        <SaveToggle jobTitle={`${job.company} ${job.title}`} />
      </TableCell>
    </TableRow>
  );
}

export function JobTable({ jobs, asOf }: { jobs: JobPosting[]; asOf: string }) {
  return (
    <DataTable columns={JOB_COLUMNS} label="채용 공고 목록">
      {jobs.map((job) => (
        <JobRow key={job.id} job={job} asOf={asOf} />
      ))}
    </DataTable>
  );
}
