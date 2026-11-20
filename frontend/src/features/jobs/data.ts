import { apiGet } from "@/lib/api";
import type { FeedResponse, JobRegion, JobSort, PostingDetailResponse } from "./types";

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
  /** true면 지역인재 전형이 있을 수 있는 공고(이전 공공기관 등)만 */
  regionalTalent?: boolean;
};

/** B-03 맞춤 피드 */
export function fetchFeed({
  sort,
  region,
  keyword,
  cursor,
  limit = FEED_PAGE_SIZE,
  regionalTalent,
}: FeedQuery): Promise<FeedResponse> {
  return apiGet<FeedResponse>(`${BASE}/postings`, {
    sort,
    region,
    keyword: keyword?.trim(),
    cursor,
    limit,
    regionalTalent: regionalTalent ? "true" : undefined,
  });
}

/** B-04 공고 상세 */
export function fetchPosting(jobPostingId: string): Promise<PostingDetailResponse> {
  return apiGet<PostingDetailResponse>(`${BASE}/postings/${encodeURIComponent(jobPostingId)}`);
}
