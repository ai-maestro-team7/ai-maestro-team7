import { formatDday, formatMonthDay } from "@/lib/format";
import type { CareerType, EmploymentType, JobRegion, JobSort, MatchLevel, OrgType, Salary } from "./types";

/** 적합도 문구 (docs/api.md §6.3). 점수 숫자는 보여주지 않는다. */
export const MATCH_LABELS: Record<MatchLevel, string> = {
  GOOD: "잘 맞아요",
  FAIR: "맞는 편이에요",
  LOW: "조금 맞아요",
};

export const SORT_LABELS: Record<JobSort, string> = {
  BUSAN_FIRST: "추천순(부산 우선)",
  DEADLINE: "마감순",
};

/**
 * 부산 우선 추천순의 정렬 기준 문구. B `copy_rules.RANKING_BASIS[BUSAN_FIRST]`와 같은 글이다.
 * 응답이 오기 전에도 같은 자리에 미리 보여 줘 화면이 밀리지 않게 한다. 응답이 오면 응답의 `ranking.basis`를 쓴다.
 */
export const BUSAN_FIRST_BASIS = "비슷하게 맞는 공고 중 부산 근무 공고를 먼저 보여드려요";

export const REGION_FILTERS: { value: JobRegion; label: string }[] = [
  { value: "ALL", label: "전체" },
  { value: "BUSAN", label: "부산" },
  { value: "CAPITAL", label: "수도권" },
  { value: "OVERSEAS", label: "해외" },
];

export const ORG_TYPE_LABELS: Record<OrgType, string> = {
  PRIVATE: "민간",
  PUBLIC_INSTITUTION: "공공기관",
  LOCAL_PUBLIC: "지방공공기관",
};

export const EMPLOYMENT_LABELS: Record<EmploymentType, string> = {
  FULL_TIME: "정규직",
  CONTRACT: "계약직",
  PART_TIME: "시간제",
  INTERN: "인턴",
  UNKNOWN: "고용 형태 확인 필요",
};

export const CAREER_LABELS: Record<CareerType, string> = {
  NEW: "신입",
  EXPERIENCED: "경력",
  ANY: "신입·경력",
  UNKNOWN: "경력 조건 확인 필요",
};

const MONEY_UNITS: Record<Salary["unit"], string> = {
  MANWON_YEAR: "만 원/년",
  MANWON_MONTH: "만 원/월",
  MANWON: "만 원",
  WON: "원",
};

/** 서버 기준 시각(`dataAsOf`)의 날짜. 없으면 오늘(한국 시간). D-day는 이 날짜로 센다. */
export function asOfDate(dataAsOf?: string): string {
  if (dataAsOf && /^\d{4}-\d{2}-\d{2}/.test(dataAsOf)) return dataAsOf.slice(0, 10);
  return new Date(Date.now() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

/** 표의 마감 칸 두 줄 (예: "12.05" / "D-15", 상시면 "채용 시 마감" / "상시") */
export function deadlineLines(closesAt: string, rolling: boolean, asOf: string): { main: string; sub: string } {
  if (rolling) return { main: "채용 시 마감", sub: "상시" };
  return { main: formatMonthDay(closesAt), sub: formatDday(closesAt, asOf) };
}

/** 급여는 공고에 적힌 값만 보여준다 (API 값, LLM이 만들지 않음). */
export function salaryText(salary?: Salary): string {
  if (!salary?.disclosed || (salary.min === undefined && salary.max === undefined)) return "공고 원문 확인";
  const unit = MONEY_UNITS[salary.unit];
  const fmt = (n: number) => n.toLocaleString("ko-KR");
  if (salary.min !== undefined && salary.max !== undefined && salary.min !== salary.max) {
    return `${fmt(salary.min)}~${fmt(salary.max)}${unit}`;
  }
  return `${fmt((salary.min ?? salary.max) as number)}${unit}`;
}

/** 표에 보이는 짧은 근거. 마감 사실은 마감 칸에 따로 있으니 뺀다. */
export function matchReason(facts: string[]): string {
  return facts.find((fact) => !fact.startsWith("마감")) ?? "";
}

/** 정적 내보내기라 공고 ID는 주소 쿼리로 넘긴다 (빌드 때 ID를 알 수 없음). */
export function jobDetailHref(jobPostingId: string): string {
  return `/jobs/detail/?id=${encodeURIComponent(jobPostingId)}`;
}

/** C 모의면접 `job` 칸은 1~50자 (B rev 55 §10.1) */
/** 공고 상세 → 면접 설정. 공고 ID를 같이 넘기면 면접 화면이 그 공고로 질문을 만들고 공고 올리기를 끈다 (#167) */
export function interviewHref(title: string, jobPostingId?: string): string {
  const params = new URLSearchParams({ job: title.slice(0, 50) });
  if (jobPostingId) params.set("posting", jobPostingId);
  return `/interview?${params.toString()}`;
}
