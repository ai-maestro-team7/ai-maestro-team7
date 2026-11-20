import { formatDday, formatMonthDay } from "@/lib/format";
import type { JobPosting, JobSort, JobTypeFilter, MatchLevel } from "./types";

/** 적합도 문구 (docs/api.md §6.3). 점수 숫자는 보여주지 않는다. */
export const MATCH_LABELS: Record<MatchLevel, string> = {
  GOOD: "잘 맞아요",
  FAIR: "맞는 편이에요",
  LOW: "조금 맞아요",
};

export const SORT_LABELS: Record<JobSort, string> = {
  RECOMMENDED: "추천순(부산 우선)",
  DEADLINE: "마감순",
};

export const JOB_TYPE_FILTERS: JobTypeFilter[] = ["전체", "정규직", "계약직", "인턴"];

export function filterJobs(jobs: JobPosting[], type: JobTypeFilter, query: string): JobPosting[] {
  const q = query.trim().toLowerCase();
  return jobs.filter((job) => {
    if (type !== "전체" && job.employmentType !== type) return false;
    if (!q) return true;
    return [job.company, job.title, ...job.skills].some((text) => text.toLowerCase().includes(q));
  });
}

/** 마감순에서 상시 공고(deadline null)는 맨 뒤에 둔다. */
export function sortJobs(jobs: JobPosting[], sort: JobSort): JobPosting[] {
  const sorted = [...jobs];
  if (sort === "RECOMMENDED") return sorted.sort((a, b) => a.recommendRank - b.recommendRank);
  return sorted.sort((a, b) => {
    if (a.deadline === b.deadline) return a.recommendRank - b.recommendRank;
    if (a.deadline === null) return 1;
    if (b.deadline === null) return -1;
    return a.deadline.localeCompare(b.deadline);
  });
}

/** 표의 마감 칸 두 줄 (예: "12.05" / "D-15", 상시면 "채용 시 마감" / "상시") */
export function deadlineLines(job: JobPosting, asOf: string): { main: string; sub: string } {
  if (!job.deadline) return { main: "채용 시 마감", sub: "상시" };
  return { main: formatMonthDay(job.deadline), sub: formatDday(job.deadline, asOf) };
}
