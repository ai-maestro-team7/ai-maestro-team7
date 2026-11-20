import { apiGet, apiGetPublic } from "@/lib/api";
import type {
  CareerFilter,
  EmploymentFilter,
  FeedResponse,
  JobRegion,
  JobSector,
  JobSort,
  PostingDetailResponse,
  PublicPostingList,
} from "./types";

/**
 * 공고 데이터는 B API에서 읽는다 (`/api/v1/opportunities`, 개발계획서2 B-03·B-04).
 * 시연 중에는 B가 새벽에 모은 DynamoDB 데이터만 읽고 공공 API를 부르지 않는다.
 */
const BASE = "/api/v1/opportunities";

/** 한 번에 받는 공고 수 (B 기본값과 같다) */
export const FEED_PAGE_SIZE = 20;

export type FeedQuery = {
  sort: JobSort;
  region: JobRegion;
  keyword?: string;
  cursor?: string;
  limit?: number;
  /** true면 공고문의 지역 조건(비수도권·이전지역 인재, 지역 제한, 거주자 우대)이 학교 지역·사는 곳과 맞을 수 있는 공고만 */
  regionalTalent?: boolean;
  /** 공기업(PUBLIC)·사기업(PRIVATE). ALL이면 거르지 않는다 */
  sector?: JobSector;
};

/** B-03 맞춤 피드 */
export function fetchFeed({
  sort,
  region,
  keyword,
  cursor,
  limit = FEED_PAGE_SIZE,
  regionalTalent,
  sector,
}: FeedQuery): Promise<FeedResponse> {
  return apiGet<FeedResponse>(`${BASE}/postings`, {
    sort,
    region,
    keyword: keyword?.trim(),
    cursor,
    limit,
    regionalTalent: regionalTalent ? "true" : undefined,
    sector: sector && sector !== "ALL" ? sector : undefined,
  });
}

export type PublicQuery = {
  sector: JobSector;
  region: JobRegion;
  career: CareerFilter;
  employment: EmploymentFilter;
  keyword?: string;
  cursor?: string;
  limit?: number;
};

/** 로그인 없이 보는 채용 공고 목록 (마감 임박순). 토큰을 붙이지 않는다. 분류가 ALL이면 보내지 않는다 */
export function fetchPublicPostings({
  sector,
  region,
  career,
  employment,
  keyword,
  cursor,
  limit = FEED_PAGE_SIZE,
}: PublicQuery): Promise<PublicPostingList> {
  const pick = (value: string) => (value === "ALL" ? undefined : value);
  return apiGetPublic<PublicPostingList>(`${BASE}/public/postings`, {
    sector: pick(sector),
    region: pick(region),
    career: pick(career),
    employment: pick(employment),
    keyword: keyword?.trim(),
    cursor,
    limit,
  });
}

/** B-04 공고 상세 */
export function fetchPosting(jobPostingId: string): Promise<PostingDetailResponse> {
  return apiGet<PostingDetailResponse>(`${BASE}/postings/${encodeURIComponent(jobPostingId)}`);
}
